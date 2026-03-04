import asyncio
import logging
from azure.storage.blob.aio import BlobServiceClient
from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def reset_blob_metadata():
    """
    Utility script to remove the 'is_processed' metadata from all files in the 
    raw emails container. This allows the Sync flow to ingest them again after
    the local database is cleared for testing purposes.
    """
    if not settings.azure_storage_connection_string:
        logger.error("Missing AZURE_STORAGE_CONNECTION_STRING")
        return

    # Use the connection string config
    blob_service_client = BlobServiceClient.from_connection_string(settings.azure_storage_connection_string)
    
    container_name = settings.blob_container_raw_emails
    container_client = blob_service_client.get_container_client(container_name)

    logger.info(f"Targeting container: {container_name}")
    
    success_count = 0
    error_count = 0

    try:
        async for blob in container_client.list_blobs():
            try:
                blob_client = container_client.get_blob_client(blob.name)
                # Fetch existing properties
                props = await blob_client.get_blob_properties()
                metadata = props.metadata or {}
                
                # Check if it was processed
                if metadata.get('is_processed') == 'true':
                    # Remove the flag
                    metadata.pop('is_processed')
                    # Update metadata on Blob
                    await blob_client.set_blob_metadata(metadata=metadata)
                    logger.info(f"Reset: {blob.name}")
                    success_count += 1
            except Exception as e:
                logger.error(f"Failed to reset {blob.name}: {e}")
                error_count += 1

        logger.info(f"Complete. Successfully reset {success_count} blobs. Errors: {error_count}")

    except Exception as e:
        logger.error(f"Failed to list blobs in container '{container_name}': {e}")
    finally:
        await blob_service_client.close()

if __name__ == "__main__":
    asyncio.run(reset_blob_metadata())
