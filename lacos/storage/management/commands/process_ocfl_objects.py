#!/usr/bin/env python
import os
import subprocess
from django.core.management.base import BaseCommand
from pathlib import Path


def find_ocfl_objects(base_dir, production_bucket=None):
    """
    Recursively find all directories containing OCFL version markers
    Exclude objects that are in the production bucket
    """
    ocfl_objects = []
    
    # Convert production_bucket to absolute path if provided
    prod_path = None
    if production_bucket:
        prod_path = os.path.abspath(production_bucket)
    
    for root, dirs, files in os.walk(base_dir):
        # Skip the production bucket directory
        if prod_path and os.path.abspath(root).startswith(prod_path):
            # Skip this directory and all subdirectories
            dirs[:] = []  # Clear the dirs list to prevent os.walk from descending into subdirectories
            continue
            
        # Check if this directory has an OCFL version marker
        if any(f.startswith("0=ocfl_object_") for f in files):
            # Get the relative path from the base directory
            rel_path = os.path.relpath(root, base_dir)
            ocfl_objects.append(rel_path)
    
    return ocfl_objects


class Command(BaseCommand):
    help = 'Process all OCFL objects in a directory recursively'

    def add_arguments(self, parser):
        parser.add_argument('base_dir', type=str, help='Base directory to search for OCFL objects')
        parser.add_argument('--ingest-bucket', type=str, required=True,
                          help='Path to ingest bucket (local path or s3:// URL)')
        parser.add_argument('--production-bucket', type=str, required=True,
                          help='Path to production bucket (local path or s3:// URL)')
        parser.add_argument('--dry-run', action='store_true', 
                          help='Show what would be done without making changes')
        parser.add_argument('--force', action='store_true', 
                          help='Force operation even if validation fails')

    def handle(self, *args, **options):
        base_dir = options['base_dir']
        ingest_bucket = options['ingest_bucket']
        production_bucket = options['production_bucket']
        dry_run = options.get('dry_run', False)
        force = options.get('force', False)
        
        # Find all OCFL objects, excluding those in the production bucket
        self.stdout.write(f"Searching for OCFL objects in {base_dir}, excluding {production_bucket}...")
        ocfl_objects = find_ocfl_objects(base_dir, production_bucket)
        
        if not ocfl_objects:
            self.stdout.write(self.style.WARNING(f"No OCFL objects found in {base_dir}"))
            return
        
        self.stdout.write(self.style.SUCCESS(f"Found {len(ocfl_objects)} OCFL objects to process"))
        
        # Process each OCFL object
        for obj_path in ocfl_objects:
            self.stdout.write(self.style.NOTICE(f"\nProcessing: {obj_path}"))
            
            # Build the command
            cmd = [
                "python", "manage.py", "standardize_ocfl_structure", 
                obj_path,
                "--ingest-bucket", ingest_bucket,
                "--production-bucket", production_bucket
            ]
            
            if dry_run:
                cmd.append("--dry-run")
            
            if force:
                cmd.append("--force")
            
            # Run the command
            try:
                result = subprocess.run(cmd, check=True, capture_output=True, text=True)
                self.stdout.write(result.stdout)
            except subprocess.CalledProcessError as e:
                self.stdout.write(self.style.ERROR(f"Error processing {obj_path}: {e}"))
                if hasattr(e, 'stdout') and e.stdout:
                    self.stdout.write(self.style.ERROR(e.stdout))
                if hasattr(e, 'stderr') and e.stderr:
                    self.stdout.write(self.style.ERROR(e.stderr)) 