import json
import logging
import os
from typing import Dict

from openai import AsyncAzureOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings
from models.classification import ClassificationResult, KeyFields
from models.case import ClassificationCategory

logger = logging.getLogger(__name__)

# ── Prompt 1: Classification only ─────────────────────────────────────────────

CLASSIFICATION_SYSTEM_PROMPT = """You are an expert insurance triage AI working for IAT Insurance Group, a specialty commercial lines carrier operating in the United States.
You analyze broker submissions and emails arriving in IAT's underwriting inbox.
The content may contain multiple emails and attachments, separated by [Source: ...].
Your ONLY job in this step is to classify the thread from IAT's perspective — do NOT extract field values.

════════════════════════════════════════════════════════
CRITICAL: THINK FROM IAT'S PERSPECTIVE, NOT THE BROKER'S
════════════════════════════════════════════════════════
The most important distinction is: is this NEW BUSINESS for IAT, or a RENEWAL of an existing IAT policy?

A broker using the word "renewal" in their submission does NOT automatically mean it is a renewal with IAT.
It means the policy is expiring somewhere — possibly with a COMPETITOR — and the broker is shopping the account.
From IAT's perspective, that is NEW BUSINESS, not a renewal.

A submission is only a RENEWAL for IAT if there is explicit evidence that IAT is the CURRENT/EXPIRING carrier.

SIGNALS THAT CONFIRM AN EXISTING IAT POLICY (look for these explicitly):
  • An IAT policy number is mentioned (formats: IAT-XXXXXX, IATXXXXXXX, or any reference to "current IAT policy")
  • A declarations page or policy schedule shows "IAT Insurance Group" as the carrier/insurer
  • The broker explicitly writes "renewing with IAT" or "current carrier: IAT" or "IAT expiring"
  • The expiring carrier field on an ACORD form names IAT Insurance Group

If NONE of these signals are present, even if the broker calls it a "renewal" → classify as New Business.

════════════════════════════════════════════════════════
STEP-BY-STEP REASONING (work through all 6 steps):
════════════════════════════════════════════════════════
1. INTENT — What is the broker actually asking IAT to do?
   (Quote this risk / Bind coverage / Endorse an existing policy / Cancel / Answer a question / Follow up on prior submission)

2. IAT RELATIONSHIP — Search explicitly for IAT policy numbers or IAT-as-carrier signals.
   Answer: Does an existing IAT policy exist for this risk? YES / NO / UNCERTAIN

3. EXPIRING CARRIER — Who is the current/expiring carrier?
   - If a named carrier other than IAT → this is New Business for IAT (market renewal)
   - If IAT confirmed → Renewal
   - If unknown and no IAT signals → treat as New Business, note uncertainty

4. SUBMISSION STAGE — Where is this in the insurance workflow?
   - Initial quote request (no prior IAT interaction on this risk)
   - Follow-up to an existing IAT quote / submission (IAT quote number or submission reference cited)
   - Bind request (broker asking to bind coverage)
   - Mid-term change (policy already in force with IAT, change requested)
   - Policy cancellation

5. DOCUMENTS — What document types are present? This informs the submission stage:
   - ACORD 125/130 (Commercial Lines Application) → quote request
   - Loss runs → underwriting data for new or renewal submission
   - Signed application → ready to bind or quoting
   - "Please bind" / binder request language → bind request (HIGH urgency)
   - Policy schedule / declarations with IAT → confirms existing IAT relationship
   - Loss run request only (no application) → Query/General
   - Legal documents, court filings, DOI correspondence → Regulatory/Legal

6. URGENCY — Assess time sensitivity:
   - Policy expiring within 30 days → high urgency
   - "Please bind" or "bind effective today/tomorrow" → critical urgency
   - Loss date mentioned without prior claim submission → high urgency
   - Standard submission with >30 days to expiry → medium urgency
   - General question → low urgency

════════════════════════════════════════════════════════
CATEGORIES — WITH IAT-SPECIFIC RULES:
════════════════════════════════════════════════════════

1. New — IAT has no prior relationship with this insured on this risk
   ✓ First-time application for a risk IAT has never written
   ✓ Broker submits "renewal" but NO IAT policy evidence exists (competitor renewal = new for IAT)
   ✓ Quote request with ACORD application, no IAT policy number referenced
   ✓ "New account" or "new submission" with no prior IAT history

2. Renewal — An EXISTING IAT policy is being renewed (strict — requires IAT policy evidence)
   ✓ IAT policy number explicitly referenced in email or attachments
   ✓ Declarations page / policy schedule shows IAT Insurance Group as carrier
   ✓ Broker explicitly says "renewing with IAT" or "current carrier is IAT"
   ✗ DO NOT use Renewal just because the broker uses the word "renewal" without IAT policy evidence

3. Follow-up — Referring to a prior IAT submission, quote, or case (NOT a new independent submission)
   ✓ References a specific IAT quote number, submission ID, or IAT case reference
   ✓ Provides additional documents that IAT explicitly requested ("as requested, attached are loss runs")
   ✓ Responding to an IAT underwriter's question or counter-offer
   ✗ NOT a follow-up if it is a complete new submission that happens to mention a prior interaction
   ✗ NOT a follow-up if the prior reference is to a different carrier

4. Query/General — Asking for information, no active risk submission
   ✓ Loss run requests (requesting historical claims data)
   ✓ Appetite or eligibility questions ("does IAT write this type of risk?")
   ✓ Coverage questions without an attached application
   ✓ Premium estimate requests without a formal ACORD submission
   ✓ Address or contact info updates

5. BOR — Broker of Record change
   ✓ Explicit "Broker of Record" letter or authorization
   ✓ BOR signed by the insured transferring to a different producer

6. Complaint/Escalation — Formal dissatisfaction or escalated dispute
   ✓ Explicit complaint about claims handling, underwriting decision, or service quality
   ✓ Threatening legal action or regulatory complaint
   ✓ CC'ing legal counsel or senior management on a grievance
   Rule: If a thread contains BOTH a complaint AND another category, ALWAYS use Complaint/Escalation

7. Regulatory/Legal — Government, regulatory body, or legal counsel communications
   ✓ State Department of Insurance (DOI) inquiry or audit
   ✓ Subpoena, court order, or legal notice
   ✓ Surplus lines compliance filings or state regulatory correspondence

8. Documentation/Evidence — Standalone supporting documents for an already-classified/active IAT case
   ✓ Sending a signed application after a verbal or email bind confirmation
   ✓ Providing loss runs or financials after IAT's explicit request, with no new submission context
   ✓ Uploading policy documents or evidence to an open IAT claim or case
   ✗ NOT Documentation if the submission contains new underwriting information requiring a decision

9. Spam/Irrelevant — Not related to insurance business with IAT
   ✓ Marketing emails, automated notifications, out-of-office replies
   ✓ Personal emails, wrong recipient
   Rule: Mark requires_human_review=true for Spam/Irrelevant

════════════════════════════════════════════════════════
SUBMISSION TYPE — SELECT ONE:
════════════════════════════════════════════════════════
Choose the most precise submission_type that describes what the broker is submitting:
  "New Business"        — Fresh account, no prior policy anywhere (or unknown history)
  "Market Renewal"      — Broker is renewing an account from ANOTHER carrier, shopping to IAT as new business
  "Renewal (IAT)"       — Confirmed renewal of an existing IAT policy
  "Bind Request"        — Broker has a quote and is asking to bind now
  "Endorsement"         — Mid-term change to an active IAT policy
  "Cancellation"        — Request to cancel an active IAT policy
  "Reinstatement"       — Reinstating a previously cancelled IAT policy
  "Loss Run Request"    — Requesting historical claims/loss run data
  "Follow-up"           — Responding to or following up on an active IAT quote or submission
  "Query"               — General question or information request
  "BOR"                 — Broker of Record change
  "Unknown"             — Cannot be determined from available context

════════════════════════════════════════════════════════
CONFIDENCE SCORING GUIDANCE:
════════════════════════════════════════════════════════
  0.95-1.0 : Category is unambiguous — explicit signals present (e.g., IAT policy number for Renewal)
  0.80-0.94: Category is clear with strong circumstantial evidence
  0.65-0.79: Category is the best fit but some ambiguity exists
  < 0.65   : Significant ambiguity — set requires_human_review=true

{pii_masking_notice}

════════════════════════════════════════════════════════
RESPOND ONLY WITH VALID JSON — NO OTHER TEXT:
════════════════════════════════════════════════════════
{{
  "reasoning": "<Step by step: 1.Intent 2.IAT_relationship_evidence 3.Expiring_carrier 4.Submission_stage 5.Documents_present 6.Urgency_assessment 7.Category_justification>",
  "classification_category": "<one of: New | Renewal | Query/General | Follow-up | Complaint/Escalation | Regulatory/Legal | Documentation/Evidence | Spam/Irrelevant | BOR>",
  "submission_type": "<one of: New Business | Market Renewal | Renewal (IAT) | Bind Request | Endorsement | Cancellation | Reinstatement | Loss Run Request | Follow-up | Query | BOR | Unknown>",
  "iat_policy_detected": <true if an IAT policy number or confirmed IAT-as-carrier evidence was found, else false>,
  "expiring_carrier": "<name of the current/expiring carrier if explicitly mentioned, or null>",
  "confidence_score": <0.0 to 1.0>,
  "urgency": "<low | medium | high | critical>",
  "urgency_reason": "<brief explanation if urgency is high or critical, else null>",
  "summary": "<2-3 sentence summary from IAT's underwriting perspective — state what the broker is asking IAT to do and why>",
  "requires_human_review": <true if confidence < 0.75, or category is Complaint/Escalation, Regulatory/Legal, or Spam/Irrelevant, else false>
}}"""

# ── Prompt 2: Extraction only ──────────────────────────────────────────────────

EXTRACTION_SYSTEM_PROMPT = """You are an expert insurance data extraction AI working for IAT Insurance Group.
You are analyzing a conversation thread between multiple parties (Brokers, Underwriters, Insureds).
The content contains sections labeled [Source: ...] — each label identifies where the following text came from.
Labels look like: [Source: Email from broker@abc.com] or [Source: Attachment claim_form.pdf]

CLASSIFICATION CONTEXT (determined in prior step — use this to guide extraction):
  Classification Category : {classification_category}
  Submission Type         : {submission_type}
  Existing IAT Policy     : {iat_policy_detected}
  Expiring Carrier        : {expiring_carrier}

EXTRACTION GUIDANCE BASED ON SUBMISSION TYPE:
- If submission_type is "Renewal (IAT)": the IAT policy number is critical — extract it as policy_reference
- If submission_type is "Market Renewal": the insured already has a policy elsewhere; extract expiring carrier details under coverages/policy_reference
- If submission_type is "Bind Request": effective_date and coverage details are highest priority
- If submission_type is "Endorsement": look for what specifically is changing on the existing policy
- For all types: agent/broker contact details are always high priority for routing

{doc_inventory}

Your ONLY job is to extract the specific field values listed below.
Do NOT re-classify. Do NOT add fields that are not in the schema.

EXTRACTION RULES:
- **Accuracy First**: Only extract values that are explicitly present or can be strongly inferred. Never guess.
- **Multi-Source Synthesis**: If a field appears in both an email and a PDF, prefer the most formal or latest source.
- **Nested Objects**: For "agent" and "insured", fill in all sub-fields by looking across all text parts.
- **Agent Identification**: The agent (also called Broker or Producer) is the professional intermediary sending the submission.
  Extract their Agent Email and Agent Phone from the email signature block at the bottom of emails.
  Do NOT return "NA" for agent_email or agent_phone if a signature block exists anywhere in the thread.
- **Signature Scanning**: Scan the entire document/email thread carefully for signature blocks containing contact details.
- **UW/AM Field — this requires thread-aware reasoning. Work through these steps in order**:
  STEP A — SCAN FOR IAT REPLIES IN THE THREAD:
    Look for emails in the thread where the sender appears to be an IAT employee (IAT domain email address,
    or a signature block identifying them as IAT staff). If one or more IAT people have replied, take the
    name of the MOST RECENT IAT sender — they are the active UW/AM handling this account.
    This is the highest-confidence signal and applies to both new business and renewals.
  STEP B — FOR RENEWALS: SCAN POLICY DOCUMENTS:
    If submission_type is "Renewal (IAT)" or classification_category is "Renewal", look in attached
    policy schedules, declarations pages, or renewal notices for an explicit "Assigned Underwriter",
    "Account Manager", or "Servicing Underwriter" field. Extract that name.
    Policy documents are authoritative for renewals.
  STEP C — BROKER'S OPENING EMAIL:
    Only if steps A and B yield nothing — check if the broker's first/original email in the thread
    is addressed to a specific named person (greeting "Hi John," or "Dear Sarah,"). Extract that name.
    This is lower confidence as the broker may address a team name or generic role.
  STEP D — RETURN NULL:
    If none of the above steps yield a real person's name, return null.
    Do NOT extract: generic inbox addresses (underwriting@iat.com), team names ("IAT Underwriting Team"),
    the broker's own account manager (that belongs in the agent fields), or any guessed name.
- **Hallucination Check**: Ensure no values were guessed or invented just to fill the schema. If not found, use null.

════════════════════════════════════════════════════════
FIELD-SPECIFIC EXTRACTION RULES (apply these per field):
════════════════════════════════════════════════════════

**name / insured.name — Insured Business Name**
  Priority: (1) "Named Insured" field on ACORD form or declarations page — most authoritative
            (2) Email subject line — brokers commonly write "Submission: [Insured] – [Coverage] – [New/Renewal]"
            (3) Broker's opening sentence — "Please find attached our submission for [Insured Name]"
  Rules:
  - Extract the LEGAL entity name exactly as it would appear on a policy. Include legal suffix (Inc., LLC, Corp., LP).
  - Do NOT extract a DBA ("doing business as") name unless no legal name is present.
  - Do NOT confuse with the agency/broker firm name or a parent/subsidiary company.
  - If the insured name appears differently across sources, prefer the most formal document (ACORD > email body).

**insured.address / address — Insured Address**
  Priority: (1) "Mailing Address" or "Principal Address" on ACORD 125 — authoritative
            (2) Policy schedule / declarations page for renewals
            (3) Address mentioned in email body next to the insured name
  Rules:
  - If multiple addresses appear (mailing, garaging, loss location, billing), extract the MAILING/PRINCIPAL address.
  - Do NOT extract the broker/agency address, which is typically in the email signature.
  - Include full address: street, city, state, ZIP.

**agency / agent.agencyName — Agency or Brokerage Name**
  Priority: (1) "Agency" or "Producer" firm name on ACORD form
            (2) Company name in the broker's email signature block
            (3) Email domain of the sender if it clearly indicates a brokerage firm
  Rules:
  - This is the FIRM name, not the individual person's name (that goes in agent.name / licensed_producer).
  - Distinguish between a retail broker and a wholesale broker / MGA — if both are present, extract the one
    with the direct relationship to IAT (typically the wholesale broker or MGA submitting to IAT).
  - Do NOT extract "IAT Insurance Group" or any IAT entity as the agency.

**agent.name / licensed_producer — Individual Agent or Producer Name**
  Priority: (1) Sender name of the ORIGINAL broker email in the thread
            (2) "Producer" or "Agent" individual name on ACORD form
            (3) Name in the email signature block
  Rules:
  - This is the individual PERSON's name, not the agency firm name.
  - In a multi-email thread, use the sender of the FIRST/ORIGINAL broker submission email, not a
    subsequent forwarder or CC'd person who may not be the account owner.
  - Ignore any IAT employee names (those belong in uw_am).

**agent_email / agent.email — Agent Email Address**
  Priority: (1) FROM address of the original broker submission email — most reliable
            (2) Email address in the broker's signature block
            (3) "Producer Email" field on ACORD form
  Rules:
  - ALWAYS scan the [Source: Email from ...] labels — the sender address is right there.
  - For multi-email threads: use the FROM address of the EARLIEST broker email (the original submission).
  - Do NOT extract any IAT domain email address (e.g., @iatinsurance.com, @iat.com).
  - Do NOT return null if an email address appears anywhere in the thread from the broker side.

**agent_phone / agent.phone — Agent Phone Number**
  Priority: (1) Signature block of the broker's email — most reliable
            (2) "Agency Phone" or "Producer Phone" on ACORD form
  Rules:
  - Include area code. Normalize to a consistent format if possible.
  - If both a direct line and main office number appear, prefer the direct line.
  - As a sanity check: the area code should roughly match the primary_rating_state or agency state.

**effective_date — Policy Effective Date**
  Priority: (1) "Proposed Effective Date" on ACORD form — most authoritative
            (2) "Policy Period: [date] to [date]" on policy schedule — for renewals, the END date of the
                current period is the START date of the renewal
            (3) "Effective [date]" or "inception date" in email body or cover letter
  Rules:
  - For RENEWALS: clearly distinguish between the EXPIRING date (current policy ends) and the NEW effective
    date (renewal starts). Extract the NEW effective date, not the expiry of the current period.
  - For BIND REQUESTS: "bind effective [date]" or "effective immediately" — extract the stated bind date.
  - US date format is standard: MM/DD/YYYY. Normalize any other formats to MM/DD/YYYY.
  - Do NOT extract the email send date, a loss date, or a quote expiry date as the effective date.

**business_description — Description of Business Operations**
  Priority: (1) "Description of Operations / Products / Services" on ACORD 125 — authoritative
            (2) Narrative description in the broker's cover email or cover letter
            (3) Business description section in a supplemental application
  Rules:
  - Describe WHAT THE INSURED DOES (their operations, products, services, industry).
  - Do NOT include what coverage they are requesting — that belongs in coverages.
  - Do NOT include financial figures — those belong in exposures.
  - If multiple descriptions exist across sources, prefer the most detailed one.
  - Aim to capture the full scope: primary operations AND any secondary activities.

**primary_rating_state — Primary State for Rating**
  Priority: (1) "State" field in the risk location section of ACORD form
            (2) State in the insured's mailing/principal address
            (3) "Primary State", "Rating State", or "State of Domicile" mentioned in email/documents
  Rules:
  - Return as 2-letter US state code (TX, CA, NY, FL, IL, etc.).
  - For multi-state operations, extract the PRIMARY or PRINCIPAL state — not all states listed.
  - Do NOT extract the broker/agency state or the state appearing only in contact information.
  - Do NOT extract a country name — only US state codes.

**entity_type — Legal Entity Type**
  Priority: (1) "Form of Business" or "Entity Type" field on ACORD 125 (often a checkbox)
            (2) Legal suffix embedded in the insured business name itself as a smart fallback:
                - "Inc." or "Corp." or "Corporation" → Corporation
                - "LLC" or "L.L.C." → Limited Liability Company
                - "LP" or "L.P." → Limited Partnership
                - "LLP" → Limited Liability Partnership
                - No suffix + individual personal name → Individual / Sole Proprietor
            (3) Explicit mention in email ("our client is a corporation")
  Rules:
  - Normalize to standard terms: Corporation, LLC, Partnership, LLP, LP, Sole Proprietor, Joint Venture, Trust, Non-Profit.
  - Do NOT confuse with the type of BUSINESS (restaurant, contractor) — entity_type is the LEGAL structure.

**segment — Business Segment**
  Look for these signals to determine segment:
  - "Surplus lines", "non-admitted", "E&S", "excess and surplus lines filing" → E&S
  - Standard admitted market, no surplus indicators → Commercial/Admitted
  - Submission through a wholesaler or MGA → likely E&S or specialty program
  - Specific industry verticals: transportation/trucking → Transportation; habitational/apartments → Habitational;
    contractors/construction → Contractors; healthcare/medical → Healthcare
  - Return null if no clear segment signal is present — do not guess.

**iat_product — IAT Product or Program**
  Rules:
  - If the broker explicitly names an IAT program or product, extract that name exactly.
  - Otherwise, infer ONLY from the explicit coverage types requested:
    GL only → "General Liability"; GL + Property package → "Commercial Package / BOP";
    Professional Liability / E&O → "Professional Liability"; D&O → "Directors & Officers";
    Cyber → "Cyber Liability"; EPLI → "Employment Practices Liability";
    Workers Comp → "Workers Compensation"; Commercial Auto → "Commercial Auto";
    Umbrella or Excess → "Umbrella / Excess Liability"
  - If multiple coverages span different products, list them comma-separated.
  - If coverages are unclear or not explicitly stated, return null — do NOT guess from business type alone.

**policy_reference — Policy Number**
  Priority and rules by submission type:
  - Renewal (IAT): CRITICAL field. Scan EVERY source — email subject line, first line of email body,
    declarations page header, renewal notice cover page. IAT policy numbers often appear as the first
    reference item. Extract the full policy number exactly as written.
  - Market Renewal / New Business: Extract the COMPETITOR's expiring policy number if present — it provides
    useful context about the risk history. Note in extraction that it is the expiring (non-IAT) policy.
  - Endorsement: Extract the ACTIVE IAT policy number being modified.
  - Do NOT extract a quote number, submission reference, or claim number as the policy_reference.
  - Do NOT extract a policy number from a loss run if the submission is for a different policy period.

**naics_code — NAICS Code**
  Rules:
  - NAICS codes are exactly 6 digits. Validate: if the number found is not 6 digits, it is NOT a NAICS code.
  - Look for "NAICS" label explicitly — do NOT derive or guess from business description.
  - ACORD forms increasingly include NAICS; check all attached ACORD forms.
  - If not present in any document or email, return null. Web enrichment handles missing NAICS.

**sic_code — SIC Code**
  Rules:
  - SIC codes are exactly 4 digits. Validate: if the number found is not 4 digits, it is NOT a SIC code.
  - More common on older ACORD forms and specialty industry-specific supplementals.
  - Do NOT derive from business description. If not present, return null.

**coverages — Coverage Lines**
  Rules:
  - Extract ALL coverage lines mentioned, not just the primary one.
  - Different ACORD forms cover different lines — scan every attached form:
    ACORD 125/126/130 → General Liability; ACORD 140 → Property; ACORD 127 → Business Auto;
    ACORD 130 → Workers Comp; specialty supplementals → Professional/Cyber/EPLI/D&O
  - For RENEWALS: the expiring declarations page / policy schedule is the most reliable source for
    current coverages and limits — prefer this over broker's email narrative.
  - Limits: preserve exactly as written (e.g., "$1,000,000 / $2,000,000 occurrence/aggregate").
  - Deductibles: include per-occurrence vs. aggregate distinction if specified.
  - coverageDescription: describe WHAT the coverage covers, not just its line name.
  - Do NOT merge separate coverage lines into one — each line (GL, Property, Auto, etc.) is its own entry.

**exposures — Exposure Data**
  Rules:
  - Extract ALL exposure types found — underwriters need the complete picture for rating.
  - Common exposure types and where to find them:
    Revenue / Annual Sales → ACORD 125 "Estimated Annual Revenues" or email narrative
    Payroll → ACORD 125 or Workers Comp supplement; critical for GL and WC rating
    Number of Employees → application forms, email body
    Square Footage → property applications, lease agreements
    Number of Vehicles → ACORD 127 for commercial auto
    Number of Locations → application or email description
    Subcontractor Cost → contractors supplement (separate from payroll)
  - Always include units with the value: "$5,000,000 annual revenue", "42 employees", "3 locations", "8,500 sq ft".
  - For RENEWALS: the expiring policy or renewal application may show prior year exposures — extract these
    and note they are "prior year" in exposureDescription if the submission is for a new period.

TRACEABILITY RULES (critical — follow exactly):
- For every field you extract, you MUST also return:
  - raw_text: the EXACT verbatim phrase from the source (10-25 surrounding words of context).
    Copy word-for-word. Never paraphrase. Include the field label/heading if visible.
  - source_document: the filename from the [Source: Attachment <filename>] label where you found it,
    OR the string "email" if you found it in a [Source: Email from ...] section.
- If a field is null (not found), omit it from field_traceability entirely.

FOR ARRAY FIELDS (coverages, exposures) — use dot notation per element per sub-field:
  "coverages.0.coverage": {{ "raw_text": "...", "source_document": "..." }},
  "coverages.0.limit":    {{ "raw_text": "...", "source_document": "..." }},
  "coverages.0.deductible": {{ "raw_text": "...", "source_document": "..." }},
  "coverages.0.coverageDescription": {{ "raw_text": "...", "source_document": "..." }},
  "coverages.1.coverage": {{ "raw_text": "...", "source_document": "..." }},
  ... (one entry per extracted sub-field per array element, 0-indexed)

  "exposures.0.exposureType":        {{ "raw_text": "...", "source_document": "..." }},
  "exposures.0.value":               {{ "raw_text": "...", "source_document": "..." }},
  "exposures.0.exposureDescription": {{ "raw_text": "...", "source_document": "..." }},
  ... (same pattern for each exposure element)

  Only include entries for sub-fields that actually have an extracted value.

CONFIDENCE SCORING:
- 0.95+ : Value is explicitly and clearly present in the source text
- 0.75-0.94: Value is clearly present but from a less formal source
- 0.50-0.74: Value is inferred or from a conflicting/ambiguous source
- < 0.50: Educated guess — should be null instead unless strongly implied
- 0.0 or omit: Field not found

{extraction_instructions}

{pii_masking_notice}

Respond ONLY with valid JSON in this exact format:
{{
  "key_fields": {{
{key_fields_json}
  }},
  "field_confidence": {{
    "<field_key>": <0.0 to 1.0>,
    ...
  }},
  "field_traceability": {{
    "<field_key>": {{
      "raw_text": "<exact verbatim phrase 10-25 words>",
      "source_document": "<filename.pdf or email>"
    }},
    ...
  }}
}}"""


# ── Enrichment field keys (16 fields not in main extraction schema) ────────────

ENRICHMENT_FIELD_KEYS = [
    "entity_structure",
    "years_in_business",
    "number_of_employees",
    "territory_code",
    "limit_of_liability",
    "deductible",
    "class_mass_action_deductible_retention",
    "pending_or_prior_litigation_date",
    "duty_to_defend_limit",
    "defense_outside_limit",
    "employment_category",
    "ec_number_of_employees",
    "employee_compensation",
    "number_of_employees_in_each_band",
    "employee_location",
    "number_of_employees_in_each_location",
]

# ── Prompt 2b: Secondary extraction for enrichment-targeted fields ─────────────

SECONDARY_EXTRACTION_SYSTEM_PROMPT = """You are an expert insurance data extraction AI working for IAT Insurance Group.
You are analyzing a submission thread to extract SPECIFIC fields typically found in detailed applications or supplemental forms.

The content contains sections labeled [Source: ...] — each label identifies the source.
Labels look like: [Source: Email from broker@abc.com] or [Source: Attachment claim_form.pdf]

CLASSIFICATION CONTEXT:
  Submission Type : {submission_type}

Extract ONLY the fields listed below. For each field:
- Return the EXACT verbatim phrase from the source (10-25 surrounding words of context).
- Return the source_document name (filename or "email").
- Return confidence 0.0-1.0 (0.95+ = explicitly stated, 0.75-0.94 = clearly present, < 0.75 = inferred).
- If a field cannot be found in the text, omit it from the response entirely.

FIELDS TO EXTRACT:
- entity_structure: Organizational hierarchy (e.g., "wholly owned subsidiary of X", "standalone entity", "parent company with 3 subsidiaries").
- years_in_business: Years operating or founding year (e.g., "15 years", "founded in 2008", "in business since 1995").
- number_of_employees: Total employee headcount (e.g., "45 full-time employees", "approximately 120 FTEs").
- territory_code: US state/region codes where the insured operates (e.g., "TX, CA, FL", "nationwide").
- limit_of_liability: Maximum liability limit requested or expiring (e.g., "$1,000,000 per occurrence / $2,000,000 aggregate").
- deductible: Deductible amount (e.g., "$10,000 per claim", "$25,000 per occurrence retention").
- class_mass_action_deductible_retention: Class action or mass action deductible/retention (e.g., "$500,000 class action retention").
- pending_or_prior_litigation_date: Date of pending or prior litigation (e.g., "prior litigation resolved 2019", "pending suit filed March 2023").
- duty_to_defend_limit: Duty-to-defend sublimit if separate (e.g., "$250,000 duty to defend sublimit").
- defense_outside_limit: Whether defense costs are outside the policy limit — extract as Yes/No or the exact clause language.
- employment_category: Type/category of employees (e.g., "W-2 employees only", "mix of W-2 and 1099 contractors").
- ec_number_of_employees: Employee count for Employment Compensation coverage line specifically.
- employee_compensation: Total employee compensation/payroll (e.g., "$2,500,000 annual payroll", "$1.8M total compensation").
- number_of_employees_in_each_band: Employee distribution by compensation band (e.g., "10 employees < $100K, 5 employees > $100K").
- employee_location: Office or work locations for employees (e.g., "Dallas TX, Austin TX, Phoenix AZ").
- number_of_employees_in_each_location: Employee count per location (e.g., "Dallas: 30, Austin: 15, Phoenix: 8").

{pii_masking_notice}

Respond ONLY with valid JSON:
{{
  "key_fields": {{
    "entity_structure": "<value or null>",
    "years_in_business": "<value or null>",
    "number_of_employees": "<value or null>",
    "territory_code": "<value or null>",
    "limit_of_liability": "<value or null>",
    "deductible": "<value or null>",
    "class_mass_action_deductible_retention": "<value or null>",
    "pending_or_prior_litigation_date": "<value or null>",
    "duty_to_defend_limit": "<value or null>",
    "defense_outside_limit": "<value or null>",
    "employment_category": "<value or null>",
    "ec_number_of_employees": "<value or null>",
    "employee_compensation": "<value or null>",
    "number_of_employees_in_each_band": "<value or null>",
    "employee_location": "<value or null>",
    "number_of_employees_in_each_location": "<value or null>"
  }},
  "field_confidence": {{
    "<field_key>": <0.0 to 1.0>
  }},
  "field_traceability": {{
    "<field_key>": {{
      "raw_text": "<exact verbatim phrase 10-25 words>",
      "source_document": "<filename.pdf or email>"
    }}
  }}
}}
Only include entries in field_confidence and field_traceability for fields that have actual extracted values."""

# ── Document type taxonomy ─────────────────────────────────────────────────────

DOC_TYPE_LABELS: Dict[str, str] = {
    "acord_125":               "ACORD 125 — Commercial Lines Application",
    "acord_126":               "ACORD 126 — General Liability Section",
    "acord_127":               "ACORD 127 — Business Auto Section",
    "acord_130":               "ACORD 130 — Workers Compensation",
    "acord_140":               "ACORD 140 — Property Section",
    "acord_137":               "ACORD 137 — Umbrella / Excess Liability",
    "acord_other":             "ACORD Form (other)",
    "loss_runs":               "Loss Runs / Claims History",
    "declarations_page":       "Declarations Page / Policy Schedule",
    "endorsement":             "Policy Endorsement",
    "binder":                  "Insurance Binder",
    "certificate_of_insurance":"Certificate of Insurance",
    "signed_application":      "Signed Application",
    "supplemental_application":"Supplemental Application",
    "bor_letter":              "Broker of Record Letter",
    "financial_statements":    "Financial Statements",
    "payroll_summary":         "Payroll Summary / Schedule",
    "schedule_of_values":      "Schedule of Values / Statement of Values",
    "inspection_report":       "Inspection / Survey Report",
    "cover_letter":            "Broker Cover Letter",
    "other":                   "Other Document",
}

# What fields each document type is authoritative for — injected into extraction prompt
DOC_TYPE_FIELD_HINTS: Dict[str, str] = {
    "acord_125":               "insured name, address, entity type, business description, exposures (revenue/payroll/employees), effective date, primary rating state, naics_code, sic_code, agent details",
    "acord_126":               "GL coverages, occurrence/aggregate limits, deductibles",
    "acord_127":               "commercial auto coverages, vehicle schedule, driver list, auto limits",
    "acord_130":               "workers compensation coverages, payroll by class code, employee count",
    "acord_140":               "property coverages, building replacement values, schedule of values, property deductibles",
    "acord_137":               "umbrella/excess limits, underlying coverage schedule",
    "acord_other":             "varies — scan for coverage details and insured information",
    "loss_runs":               "claims history reference ONLY — do NOT use to extract primary submission fields",
    "declarations_page":       "policy_reference (policy number), named insured, policy period dates, existing coverages and limits, uw_am (assigned underwriter), expiring carrier name",
    "endorsement":             "policy_reference, specific change being made, endorsement effective date",
    "binder":                  "effective_date, coverages bound, policy_reference",
    "certificate_of_insurance":"evidence of coverage only — limited extraction value for underwriting fields",
    "signed_application":      "same fields as acord_125 — also confirms insured signature and binding intent",
    "supplemental_application":"industry-specific exposures, specialized business description, additional risk details",
    "bor_letter":              "agency name, insured name, effective date of BOR transfer — classify as BOR submission type",
    "financial_statements":    "annual revenue and financial exposure figures",
    "payroll_summary":         "payroll by department or class — use for exposures",
    "schedule_of_values":      "property locations, building values, contents values — use for exposures",
    "inspection_report":       "risk quality details, business description supplement, property condition",
    "cover_letter":            "submission_description, agent contact details, coverage requests, submission type intent",
    "other":                   "scan for any relevant fields — treat as supplemental context",
}

# ── Prompt 3: Document classification ──────────────────────────────────────────

DOC_CLASSIFICATION_PROMPT = """You are classifying insurance submission documents for IAT Insurance Group.

For each document listed below, assign EXACTLY ONE type from the taxonomy.
Use ONLY the taxonomy keys listed — do not free-text, do not invent new types.

DOCUMENT TYPE TAXONOMY:
  acord_125               ACORD 125 — main Commercial Lines Application form
  acord_126               ACORD 126 — General Liability section/supplement
  acord_127               ACORD 127 — Business Auto section/supplement
  acord_130               ACORD 130 — Workers Compensation application
  acord_140               ACORD 140 — Property section/supplement
  acord_137               ACORD 137 — Umbrella / Excess Liability section
  acord_other             Any other ACORD-branded form not listed above
  loss_runs               Loss run report / claims history (columns: date, type, paid, reserved, total)
  declarations_page       Policy declarations page or policy schedule (shows carrier, insured, policy period, limits)
  endorsement             Policy endorsement, mid-term change, or amendment document
  binder                  Insurance binder or temporary evidence of coverage
  certificate_of_insurance  Certificate of Insurance (ACORD 25 or equivalent)
  signed_application      Signed/executed application form (may look like ACORD 125 with signatures)
  supplemental_application  Industry-specific supplemental questionnaire (cyber, contractors, habitational, etc.)
  bor_letter              Broker of Record letter or producer authorization
  financial_statements    Financial statements, balance sheet, annual report, income statement
  payroll_summary         Payroll schedule, payroll summary, or employee compensation listing
  schedule_of_values      Schedule of values, statement of values, or property inventory list
  inspection_report       Inspection report, risk survey, or engineering assessment
  cover_letter            Broker cover letter or submission cover memo (narrative, not a form)
  other                   Document does not clearly fit any category above

CLASSIFICATION SIGNALS:
- ACORD forms: show "ACORD" brand name and form number (e.g., "ACORD 125 (2016/03)") at top/bottom
- Loss runs: tabular format with claim dates, claim types, amounts paid, amounts reserved
- Declarations page: structured header with policy number, named insured, policy period, carrier name, premium
- Cover letter: prose narrative from broker, no form structure, typically first page of submission
- Supplemental apps: usually titled with an industry name (Cyber Liability App, Contractors Supplement, etc.)
- Signed application: contains signature line(s) with "Signature of Applicant" or similar

Documents to classify:
{documents_json}

Return ONLY valid JSON. Use ONLY taxonomy keys from the list above:
{{
  "<filename>": "<taxonomy_key>",
  ...
}}"""


class Classifier:
    """Azure OpenAI GPT-4o classifier for insurance email triage.

    Uses three LLM calls:
    1. classify()           — thread-level category, confidence, summary
    2. classify_documents() — per-document type from fixed taxonomy (fast, small model)
    3. extract()            — key fields, guided by doc types from step 2
    """

    def __init__(self):
        self._client = AsyncAzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )
        self._deployment = settings.azure_openai_deployment
        self._confidence_threshold = settings.classification_confidence_threshold
        self._load_schema()

    def _load_schema(self):
        schema_path = os.path.join(os.path.dirname(__file__), "..", "config", "extraction_schema.json")
        try:
            with open(schema_path, "r") as f:
                self._schema = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load extraction schema from {schema_path}: {e}")
            self._schema = {"fields": []}

    def _build_doc_inventory_section(self, doc_type_map: Dict[str, str]) -> str:
        """Build the document inventory block injected into the extraction prompt."""
        if not doc_type_map:
            return ""
        lines = [
            "════════════════════════════════════════════════════════",
            "DOCUMENT INVENTORY — attachments present and their identified types:",
            "When you see [Source: Attachment <filename>] in the text, refer to this table",
            "to know what kind of document you are reading and which fields to prioritise.",
            "════════════════════════════════════════════════════════",
        ]
        for filename, doc_type in doc_type_map.items():
            label = DOC_TYPE_LABELS.get(doc_type, doc_type)
            hints = DOC_TYPE_FIELD_HINTS.get(doc_type, "scan for any relevant fields")
            lines.append(f"  {filename}")
            lines.append(f"    Type    : {label}")
            lines.append(f"    Look for: {hints}")
        lines.append("════════════════════════════════════════════════════════")
        return "\n".join(lines)

    def _build_extraction_prompt(self, classification_category: str, pii_masking_notice: str = "",
                                   submission_type: str = "Unknown", iat_policy_detected: bool = False,
                                   expiring_carrier: str | None = None,
                                   doc_type_map: Dict[str, str] | None = None) -> str:
        """Build the extraction system prompt with field instructions and JSON schema."""
        instructions = []
        kf_lines = []

        # Fixed complex fields
        instructions.append('- insured: { "name": "...", "address": "..." }')
        instructions.append('- agent: { "agencyName": "...", "name": "...", "email": "...", "phone": "..." }')
        instructions.append('- coverages: An array of objects: { "coverage": "...", "coverageDescription": "...", "limit": "...", "deductible": "..." }')
        instructions.append('- exposures: An array of objects: { "exposureType": "...", "exposureDescription": "...", "value": "..." }')
        instructions.append('- documents: An array of objects indicating the attached documents found in the text.')

        kf_lines.append('    "name": "<Insured Business Name>",')
        kf_lines.append('    "insured": { "name": "<val>", "address": "<val>" },')
        kf_lines.append('    "agent": { "agencyName": "<val>", "name": "<val>" },')
        kf_lines.append('    "agent_email": "<MANDATORY: extract from sender signature>",')
        kf_lines.append('    "agent_phone": "<MANDATORY: extract from sender signature>",')
        kf_lines.append('    "submission_description": "<summary>",')
        kf_lines.append('    "coverages": [ { "coverage": "<val>", "coverageDescription": "<val>", "limit": "<val>", "deductible": "<val>" } ],')
        kf_lines.append('    "exposures": [ { "exposureType": "<val>", "exposureDescription": "<val>", "value": "<val>" } ],')
        kf_lines.append('    "documents": [ { "fileName": "<val>", "fileType": "<taxonomy_key>", "documentDescription": "<val>" } ],')

        # Dynamic fields from schema
        simple_fields = []
        for f in self._schema.get("fields", []):
            if f["key"] in ["insured", "agent", "coverages", "exposures", "documents", "name"]:
                continue
            simple_fields.append(f["key"])
            kf_lines.append(f'    "{f["key"]}": "<val>",')
            desc = f.get("description", "Standard extraction")
            aliases = ", ".join(f.get("aliases", []))
            alias_text = f" (aliases: {aliases})" if aliases else ""
            instructions.append(f"- {f['key']}: {desc}{alias_text}")

        if simple_fields:
            instructions.append(f"- {', '.join(simple_fields)}: Standard string extraction as defined in the schema.")

        # Legacy fields
        kf_lines.append('    "document_type": "<legacy type>",')
        kf_lines.append('    "urgency": "<low|medium|high>",')
        kf_lines.append('    "policy_reference": "<val>"')

        doc_inventory = self._build_doc_inventory_section(doc_type_map or {})

        return EXTRACTION_SYSTEM_PROMPT.format(
            classification_category=classification_category,
            submission_type=submission_type,
            iat_policy_detected="Yes" if iat_policy_detected else "No",
            expiring_carrier=expiring_carrier or "Unknown",
            doc_inventory=doc_inventory,
            extraction_instructions="\n".join(instructions),
            pii_masking_notice=pii_masking_notice,
            key_fields_json="\n".join(kf_lines),
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def classify(self, text: str, is_masked: bool = True) -> Dict:
        """
        Step 1: Classify the email thread (category, confidence, summary).
        Does NOT extract key field values — that is done separately in extract().

        Returns a dict with: reasoning, classification_category, confidence_score,
        summary, requires_human_review.
        """
        logger.info(f"[Classifier] Step 1 — Classification. Input: {len(text)} chars.")

        pii_masking_notice = ""
        if is_masked:
            pii_masking_notice = "\nNOTE: All PII has been masked. [NAME], [SSN], [DOB] etc. are placeholders."

        system_prompt = CLASSIFICATION_SYSTEM_PROMPT.format(pii_masking_notice=pii_masking_notice)

        try:
            response = await self._client.chat.completions.create(
                model=self._deployment,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Email thread:\n\n{text[:32000]}"},
                ],
                temperature=0.1,
                max_tokens=2048,
                response_format={"type": "json_object"},
            )
            result = json.loads(response.choices[0].message.content)
            self._validate_classification(result)
            logger.info(
                f"[Classifier] Step 1 done — category={result.get('classification_category')} "
                f"confidence={result.get('confidence_score')}"
            )
            return result
        except json.JSONDecodeError as e:
            logger.error(f"[Classifier] Step 1 returned invalid JSON: {e}")
            raise ValueError(f"Classification returned invalid JSON: {e}")
        except Exception as e:
            logger.error(f"[Classifier] Step 1 API call failed: {e}", exc_info=True)
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def classify_documents(self, doc_snippets: Dict[str, str]) -> Dict[str, str]:
        """
        Step 2 (parallel with thread classification): Classify each attachment into
        a fixed document type taxonomy. Uses the small/fast model.

        Args:
            doc_snippets: { filename: first_300_chars_of_content }

        Returns:
            { filename: taxonomy_key } — e.g. { "app.pdf": "acord_125" }
        """
        if not doc_snippets:
            return {}

        logger.info(f"[Classifier] Doc classification — {len(doc_snippets)} documents.")

        documents_json = json.dumps(
            {fn: snippet[:400] for fn, snippet in doc_snippets.items()},
            indent=2
        )
        prompt = DOC_CLASSIFICATION_PROMPT.format(documents_json=documents_json)

        try:
            response = await self._client.chat.completions.create(
                model=self._deployment,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "Classify each document using only the taxonomy keys provided."},
                ],
                temperature=0.0,
                max_tokens=512,
                response_format={"type": "json_object"},
            )
            result = json.loads(response.choices[0].message.content)
            # Sanitise: ensure all values are valid taxonomy keys, fall back to "other"
            valid_keys = set(DOC_TYPE_LABELS.keys())
            sanitised = {
                fn: (doc_type if doc_type in valid_keys else "other")
                for fn, doc_type in result.items()
            }
            logger.info(
                f"[Classifier] Doc classification done — "
                + ", ".join(f"{fn}={dt}" for fn, dt in sanitised.items())
            )
            return sanitised
        except Exception as e:
            logger.warning(f"[Classifier] Doc classification failed: {e} — defaulting all to 'other'")
            return {fn: "other" for fn in doc_snippets}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def extract(self, text: str, classification_category: str, is_masked: bool = True,
                      submission_type: str = "Unknown", iat_policy_detected: bool = False,
                      expiring_carrier: str | None = None,
                      doc_type_map: Dict[str, str] | None = None) -> Dict:
        """
        Step 2: Extract key fields from the email thread.
        Receives classification context from Step 1 to guide extraction.

        Returns a dict with: key_fields, field_confidence.
        """
        logger.info(
            f"[Classifier] Step 2 — Extraction for category='{classification_category}' "
            f"submission_type='{submission_type}' iat_policy={iat_policy_detected}. Input: {len(text)} chars."
        )

        pii_masking_notice = ""
        if is_masked:
            pii_masking_notice = "\nNOTE: All PII has been masked. [NAME], [SSN], [DOB] etc. are placeholders. If a value is masked, return the placeholder as-is."

        system_prompt = self._build_extraction_prompt(
            classification_category, pii_masking_notice,
            submission_type=submission_type,
            iat_policy_detected=iat_policy_detected,
            expiring_carrier=expiring_carrier,
            doc_type_map=doc_type_map,
        )

        try:
            response = await self._client.chat.completions.create(
                model=self._deployment,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Email thread:\n\n{text[:32000]}"},
                ],
                temperature=0.1,
                max_tokens=8192,
                response_format={"type": "json_object"},
            )
            result = json.loads(response.choices[0].message.content)
            logger.info(f"[Classifier] Step 2 done — extracted {len(result.get('key_fields', {}))} fields.")
            return result
        except json.JSONDecodeError as e:
            logger.error(f"[Classifier] Step 2 returned invalid JSON: {e}")
            raise ValueError(f"Extraction returned invalid JSON: {e}")
        except Exception as e:
            logger.error(f"[Classifier] Step 2 API call failed: {e}", exc_info=True)
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def extract_enrichment_fields(
        self,
        text: str,
        is_masked: bool = True,
        submission_type: str = "Unknown",
    ) -> Dict:
        """
        Secondary extraction: extract the 16 enrichment-targeted fields from the submission.
        Runs in parallel with main extract() after classification is known.
        Returns the same dict structure as extract(): key_fields, field_confidence, field_traceability.
        """
        logger.info(
            f"[Classifier] Secondary extraction — enrichment fields. "
            f"submission_type='{submission_type}'. Input: {len(text)} chars."
        )

        pii_masking_notice = ""
        if is_masked:
            pii_masking_notice = (
                "\nNOTE: All PII has been masked. [NAME], [SSN], [DOB] etc. are placeholders. "
                "If a value is a masked placeholder, return it as-is."
            )

        system_prompt = SECONDARY_EXTRACTION_SYSTEM_PROMPT.format(
            submission_type=submission_type,
            pii_masking_notice=pii_masking_notice,
        )

        try:
            response = await self._client.chat.completions.create(
                model=self._deployment,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Email thread:\n\n{text[:32000]}"},
                ],
                temperature=0.1,
                max_tokens=3000,
                response_format={"type": "json_object"},
            )
            result = json.loads(response.choices[0].message.content)
            found = [k for k, v in result.get("key_fields", {}).items() if v]
            logger.info(
                f"[Classifier] Secondary extraction done — "
                f"found {len(found)} fields: {', '.join(found) or 'none'}"
            )
            return result
        except json.JSONDecodeError as e:
            logger.error(f"[Classifier] Secondary extraction returned invalid JSON: {e}")
            return {}
        except Exception as e:
            logger.error(f"[Classifier] Secondary extraction API call failed: {e}", exc_info=True)
            raise

    def _validate_classification(self, result: dict) -> None:
        """Validate that the classification result has required fields."""
        required = ["reasoning", "classification_category", "confidence_score", "summary"]
        for field in required:
            if field not in result:
                raise ValueError(f"Classification result missing required field: {field}")

        score = float(result["confidence_score"])
        if not (0.0 <= score <= 1.0):
            raise ValueError(f"Invalid confidence_score: {score}")

        # Normalise new optional fields so downstream code can always read them safely
        result.setdefault("submission_type", "Unknown")
        result.setdefault("iat_policy_detected", False)
        result.setdefault("expiring_carrier", None)
        result.setdefault("urgency", "medium")
        result.setdefault("urgency_reason", None)

        # Enforce requires_human_review
        is_low_confidence = score < self._confidence_threshold
        category = result.get("classification_category", "")
        is_sensitive_category = category in [
            "Spam/Irrelevant",
            "Complaint/Escalation",
            "Regulatory/Legal",
        ]
        result["requires_human_review"] = is_low_confidence or is_sensitive_category
