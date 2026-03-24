import asyncio
import time
import uuid
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from unittest.mock import MagicMock, AsyncMock

# Mocking parts of the system to test the parallel logic
import sys
import os

# Add backend to path (absolute)
sys.path.append("/home/azureuser/Documents/projects/IAT-POC/backend")

from services.pii_masker import PIIMasker
from services.extraction_service import ExtractionService, find_field_worker

# Dummy settings import if necessary
from config import settings

async def benchmark():
    print("Starting Performance Benchmark...")
    
    # 1. Test PII Masking Parallelization
    masker = PIIMasker()
    # Large enough to trigger chunks (MAX_CHUNK_SIZE is 500k, let's use 1M for real test)
    large_text = "This is a test with PII like John Doe and 123-456-7890. " * 30000 
    print(f"Benchmarking PII Masking (Sequential vs Parallel) with {len(large_text)/1024/1024:.2f} MB text...")
    
    num_cpus = multiprocessing.cpu_count()
    executor = ProcessPoolExecutor(max_workers=min(num_cpus, 8))
    
    start_seq = time.time()
    # Mocking sequential chunking for speed in benchmark
    # await masker.mask_text(large_text, "case1", "doc1") 
    print("Sequential PII Masking (skipping to avoid slow bench)...")
    end_seq = time.time()
    
    start_par = time.time()
    await masker.mask_text(large_text, "case1", "doc1", executor=executor)
    end_par = time.time()
    print(f"Parallel PII: {end_par - start_par:.4f}s")
    
    # 2. Test Bounding Box Worker
    extraction_svc = ExtractionService()
    # Dummy layout with high confidence match
    dummy_layout = {
        "pages": [{
            "width": 8.5, "height": 11, "unit": "inch",
            "words": [{"content": "Policy", "polygon": [0,0,1,0,1,1,0,1], "confidence": 0.99},
                      {"content": "Number:", "polygon": [1,0,2,0,2,1,1,1], "confidence": 0.99},
                      {"content": "123456", "polygon": [2,0,3,0,3,1,2,1], "confidence": 0.99}]
        }]
    }
    
    print("\nBenchmarking Bounding Box Worker Execution...")
    val = "123456"
    
    start_search = time.time()
    loop = asyncio.get_event_loop()
    matches = await loop.run_in_executor(executor, find_field_worker, dummy_layout, val)
    end_search = time.time()
    print(f"Field search in worker: {end_search - start_search:.4f}s")
    print(f"Found {len(matches)} matches. Best similarity: {matches[0]['similarity'] if matches else 0}")

    executor.shutdown()
    print("\nBenchmark complete.")

if __name__ == "__main__":
    asyncio.run(benchmark())
