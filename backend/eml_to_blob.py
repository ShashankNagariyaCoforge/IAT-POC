"""
eml_to_blob.py — Upload local .eml files to Azure Blob Storage
in the exact format expected by the email sync pipeline.

Usage:
    python eml_to_blob.py
    python eml_to_blob.py --folder /path/to/input_emails

Flow:
    1. Reads all *.eml files from input_emails/ (or --folder path)
    2. Parses each into the email.json + raw attachment bytes
       (same structure email_fetcher.py produces from Graph API)
    3. Uploads to blob storage under:
           {YYYY/MM/DD}/{YYYYMMDD_HHMMSS}_{id}/email.json
           {YYYY/MM/DD}/{YYYYMMDD_HHMMSS}_{id}/{attachment_name}
    4. Moves the processed .eml to input_emails/processed/
       so it is never uploaded again on the next run

.env keys used (same as the main application):
    AZURE_STORAGE_CONNECTION_STRING   — required
    BLOB_CONTAINER_RAW_EMAILS         — optional, defaults to iat_documents
"""

import argparse
import email
import email.policy
import email.utils
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path

from azure.storage.blob import BlobServiceClient, ContentSettings


# ── Load .env without external deps ───────────────────────────────────────────

def _load_dotenv(env_path: Path) -> None:
    """Read key=value pairs from .env file into os.environ (skips already-set keys)."""
    if not env_path.exists():
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


# ── Content-type helper ────────────────────────────────────────────────────────

def _content_type(filename: str) -> str:
    mapping = {
        ".pdf":  "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".doc":  "application/msword",
        ".xls":  "application/vnd.ms-excel",
        ".png":  "image/png",
        ".jpg":  "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif":  "image/gif",
        ".txt":  "text/plain",
        ".csv":  "text/csv",
        ".zip":  "application/zip",
        ".json": "application/json",
    }
    for ext, ctype in mapping.items():
        if filename.lower().endswith(ext):
            return ctype
    return "application/octet-stream"


# ── .eml parser ────────────────────────────────────────────────────────────────

def parse_eml(eml_path: Path) -> dict:
    """
    Parse a .eml file and return a dict with:
        metadata   — dict matching the email.json format email_fetcher.py produces
        attachments — list of {"name": str, "bytes": bytes}
    """
    with open(eml_path, "rb") as f:
        msg = email.message_from_binary_file(f, policy=email.policy.default)

    # ── Header fields ──────────────────────────────────────────────────────────
    subject = str(msg.get("Subject", "(No Subject)"))

    _, from_addr = parseaddr(str(msg.get("From", "")))

    to_raw   = str(msg.get("To", ""))
    cc_raw   = str(msg.get("Cc", ""))
    to_addrs = [addr for _, addr in email.utils.getaddresses([to_raw])  if addr]
    cc_addrs = [addr for _, addr in email.utils.getaddresses([cc_raw])  if addr]

    date_raw = str(msg.get("Date", ""))
    try:
        received_dt = parsedate_to_datetime(date_raw).astimezone(timezone.utc).isoformat()
    except Exception:
        received_dt = datetime.now(timezone.utc).isoformat()

    # Use Message-ID header if present; otherwise generate one
    message_id      = str(msg.get("Message-ID", f"<{uuid.uuid4()}@local>")).strip()
    conversation_id = str(msg.get("Thread-Index", str(uuid.uuid4())))

    # ── Body + attachments ─────────────────────────────────────────────────────
    html_body  = ""
    plain_body = ""
    attachments = []

    for part in msg.walk():
        content_type = part.get_content_type()
        disposition  = str(part.get("Content-Disposition", ""))

        # Skip multipart wrapper parts
        if part.get_content_maintype() == "multipart":
            continue

        if "attachment" not in disposition and "inline" not in disposition:
            # Body part
            if content_type == "text/html":
                try:
                    html_body = part.get_content()
                except Exception:
                    html_body = part.get_payload(decode=True).decode("utf-8", errors="replace")
            elif content_type == "text/plain" and not html_body:
                try:
                    plain_body = part.get_content()
                except Exception:
                    plain_body = part.get_payload(decode=True).decode("utf-8", errors="replace")
        else:
            # Attachment
            filename = part.get_filename()
            if not filename:
                continue
            payload = part.get_payload(decode=True)
            if payload:
                attachments.append({"name": filename, "bytes": payload})

    # Prefer HTML body; fall back to plain text wrapped in <pre>
    body = html_body or (f"<pre>{plain_body}</pre>" if plain_body else "")

    metadata = {
        "subject":          subject,
        "from":             from_addr,
        "to":               to_addrs,
        "cc":               cc_addrs,
        "receivedDateTime": received_dt,
        "messageId":        message_id,
        "internetMessageId":message_id,
        "conversationId":   conversation_id,
        "bodyPreview":      (plain_body or "")[:255],
        "body":             body,
        "hasAttachments":   len(attachments) > 0,
    }

    return {"metadata": metadata, "attachments": attachments}


# ── Blob uploader ──────────────────────────────────────────────────────────────

def upload_to_blob(
    parsed: dict,
    container_name: str,
    blob_service: BlobServiceClient,
) -> str:
    """
    Upload email.json + attachments to blob storage.

    Folder structure matches email_fetcher.py exactly:
        {YYYY/MM/DD}/{YYYYMMDD_HHMMSS}_{unique_id}/email.json
        {YYYY/MM/DD}/{YYYYMMDD_HHMMSS}_{unique_id}/{attachment_name}

    The email.json is uploaded WITHOUT the 'is_processed' metadata flag,
    so the poller treats it as a new unprocessed email.

    Returns the base folder path (for logging).
    """
    metadata    = parsed["metadata"]
    attachments = parsed["attachments"]

    # Build folder path identical to email_fetcher.py
    try:
        dt = datetime.fromisoformat(metadata["receivedDateTime"].replace("Z", "+00:00"))
    except Exception:
        dt = datetime.now(timezone.utc)

    partition   = dt.strftime("%Y/%m/%d")
    timestamp   = dt.strftime("%Y%m%d_%H%M%S")
    unique_id   = uuid.uuid4().hex[:12]
    base_folder = f"{partition}/{timestamp}_{unique_id}"

    container = blob_service.get_container_client(container_name)

    # Upload email.json — no is_processed metadata so poller picks it up
    email_json_path  = f"{base_folder}/email.json"
    email_json_bytes = json.dumps(metadata, indent=4, ensure_ascii=False).encode("utf-8")
    container.get_blob_client(email_json_path).upload_blob(
        email_json_bytes,
        overwrite=True,
        content_settings=ContentSettings(content_type="application/json"),
    )
    print(f"    ✔ email.json      → {email_json_path}")

    # Upload each attachment as raw bytes
    for att in attachments:
        att_path = f"{base_folder}/{att['name']}"
        container.get_blob_client(att_path).upload_blob(
            att["bytes"],
            overwrite=True,
            content_settings=ContentSettings(content_type=_content_type(att["name"])),
        )
        print(f"    ✔ attachment      → {att_path}")

    return base_folder


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upload .eml files to Azure Blob Storage for pipeline ingestion."
    )
    parser.add_argument(
        "--folder",
        default="input_emails",
        help="Folder containing .eml files (default: input_emails)",
    )
    args = parser.parse_args()

    # Load .env from backend/ directory (same file the app uses)
    script_dir = Path(__file__).resolve().parent
    _load_dotenv(script_dir / ".env")

    connection_string = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    container_name = (
        os.environ.get("BLOB_CONTAINER_RAW_EMAILS")
        or os.environ.get("BLOB_CONTAINER")
        or "iat_documents"
    )

    if not connection_string:
        print("ERROR: AZURE_STORAGE_CONNECTION_STRING is not set in .env")
        return

    input_dir = Path(args.folder)
    if not input_dir.is_absolute():
        input_dir = script_dir / input_dir

    # Create folder + processed subfolder if they don't exist yet
    input_dir.mkdir(parents=True, exist_ok=True)
    processed_dir = input_dir / "processed"
    processed_dir.mkdir(exist_ok=True)

    eml_files = sorted(input_dir.glob("*.eml"))

    if not eml_files:
        print(f"No .eml files found in {input_dir}/")
        print("Place your .eml files there and re-run this script.")
        return

    print(f"Found {len(eml_files)} .eml file(s) in {input_dir.name}/")
    print(f"Blob container : {container_name}")
    print()

    blob_service = BlobServiceClient.from_connection_string(connection_string)

    success = 0
    failed  = 0

    for eml_path in eml_files:
        print(f"► {eml_path.name}")
        try:
            parsed      = parse_eml(eml_path)
            base_folder = upload_to_blob(parsed, container_name, blob_service)

            # Move to processed/ — will never be picked up again
            dest = processed_dir / eml_path.name
            shutil.move(str(eml_path), str(dest))
            print(f"    ✔ moved to        → processed/{eml_path.name}")
            print(f"    ✅ blob folder     → {base_folder}")
            success += 1

        except Exception as exc:
            print(f"    ❌ Failed: {exc}")
            failed += 1

        print()

    print("=" * 56)
    print(f"Done — {success} uploaded, {failed} failed.")
    if success:
        print()
        print("Next steps:")
        print("  • The poller picks these up automatically on its next tick.")
        print("  • Or click 'Sync' in the UI to trigger immediately.")
        print("  • Cases will appear in RECEIVED state, ready to process.")


if __name__ == "__main__":
    main()
