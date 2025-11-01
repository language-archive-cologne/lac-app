#!/usr/bin/env python
"""Test S3 connection from Django."""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()

from lacos.storage.services.base_storage_service import BaseStorageService
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

print("\n" + "="*60)
print("S3 Connection Diagnostic Test")
print("="*60)

try:
    service = BaseStorageService()
    print(f"\n✅ Service initialized")
    print(f"   Endpoint: {service.endpoint_url}")
    print(f"   Is MinIO: {service.is_minio}")
    print(f"   Region: {service.region}")
    print(f"   Access Key: {service.access_key[:10]}...")
    
    print(f"\n🔍 Testing lazy bucket loading...")
    print(f"   Using iter_buckets() (lazy iterator)...")
    lazy_buckets = list(service.iter_buckets())
    print(f"✅ Lazy iterator found {len(lazy_buckets)} buckets:")
    for bucket in lazy_buckets:
        print(f"   - {bucket}")
    
    print(f"\n🔍 Testing get_all_accessible_buckets() (cached)...")
    all_buckets = service.get_all_accessible_buckets()
    print(f"✅ Found {len(all_buckets)} buckets (from cache or lazy fetch):")
    for bucket in all_buckets:
        print(f"   - {bucket}")
        
except Exception as e:
    print(f"\n❌ FAILED: {type(e).__name__}")
    print(f"   Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "="*60)

