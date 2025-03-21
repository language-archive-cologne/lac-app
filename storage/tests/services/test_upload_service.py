def test_get_upload_part_urls(mock_upload_service):
    """Test generating presigned URLs for multipart upload parts"""
    # First initialize a multipart upload if not already done
    global _init_result
    if _init_result is None:
        _init_result = test_initialize_multipart_upload(mock_upload_service)
    
    # Now get presigned URLs for parts
    part_count = 3
    result = mock_upload_service.get_upload_part_urls(
        s3_key=_init_result["s3_key"],
        upload_id=_init_result["upload_id"],
        part_count=part_count
    )
    
    # Check the result
    assert result["success"] is True, "Getting part upload URLs should succeed"
    assert len(result["presigned_urls"]) == part_count, f"Should generate {part_count} presigned URLs"
    assert result["s3_key"] == _init_result["s3_key"], "S3 key should match the initialization"
    assert result["upload_id"] == _init_result["upload_id"], "Upload ID should match the initialization"
    
    # Check each URL
    for i, part_url in enumerate(result["presigned_urls"]):
        assert "part_number" in part_url, "Each URL should include a part number"
        assert part_url["part_number"] == i + 1, "Part numbers should be sequential"
        assert "url" in part_url, "Each URL entry should include the actual URL"
        assert isinstance(part_url["url"], str), "URL should be a string"
        
        # Check if the URL contains the right parameters
        assert "partNumber=" in part_url["url"], "URL should include part number parameter"
        assert "uploadId=" in part_url["url"], "URL should include upload ID parameter"
    
    # Store the results for other tests
    global _parts_result
    _parts_result = result
    
    # Don't return the result - this is causing the pytest warning
    # return result

def test_generate_batch_presigned_posts(mock_upload_service):
    """Test generating multiple presigned post URLs"""
    files_metadata = [
        {"file_name": "file1.txt", "file_type": "text/plain"},
        {"file_name": "file2.txt", "file_type": "text/plain"},
        {"file_name": "file3.jpg", "file_type": "image/jpeg"}
    ]
    
    result = mock_upload_service.generate_batch_presigned_posts(
        files_metadata=files_metadata,
        path_prefix=TEST_FOLDER_NAME
    )
    
    # Check the overall result
    assert result["success"] is True, "Batch presigned URL generation should succeed"
    assert result["total_urls"] == 3, "Should generate 3 presigned URLs"
    assert len(result["presigned_posts"]) == 3, "Should have 3 presigned post results"
    assert result["total_failures"] == 0, "Should have no failures"
    
    # Check individual URLs
    for i, presigned_post in enumerate(result["presigned_posts"]):
        file_meta = files_metadata[i]
        assert presigned_post["file_name"] == file_meta["file_name"], f"File name should match for item {i}"
        assert presigned_post["s3_key"] == f"{TEST_FOLDER_NAME}/{file_meta['file_name']}", f"S3 key should include folder for item {i}"
        # Make sure we're checking for the right keys in the presigned_post
        assert "presigned_post" in presigned_post, f"Item {i} should include presigned_post data"
        assert "url" in presigned_post["presigned_post"], f"Item {i} should include URL"
        assert "fields" in presigned_post["presigned_post"], f"Item {i} should include fields"

def test_multipart_upload_large_file_simulation(mock_s3, mock_upload_service):
    """
    Test a full multipart upload flow with a simulated large file.
    
    This test simulates the typical flow of a multipart upload:
    1. Initialize the multipart upload
    2. Split the file into parts and upload each part
    3. Complete the multipart upload
    4. Verify the result
    """
    # Setup
    file_name = "simulated_large_file.dat"
    file_type = "application/octet-stream"
    path_prefix = "simulation_test"
    s3_key = f"{path_prefix}/{file_name}"
    
    # Create a simulated large file (3 parts, 5MB each to meet S3 minimum requirements)
    part_size = 5 * 1024 * 1024  # 5MB
    part_count = 3
    
    # Step 1: Initialize the multipart upload
    init_result = mock_upload_service.initialize_multipart_upload(
        file_name=file_name,
        file_type=file_type,
        path_prefix=path_prefix
    )
    
    assert init_result["success"] is True, "Multipart upload initialization should succeed"
    upload_id = init_result["upload_id"]
    
    # Step 2: Get presigned URLs for each part
    urls_result = mock_upload_service.get_upload_part_urls(
        s3_key=s3_key,
        upload_id=upload_id,
        part_count=part_count
    )
    
    assert urls_result["success"] is True, "Getting part upload URLs should succeed"
    
    # Step 3: Upload each part
    parts = []
    for part_url in urls_result["presigned_urls"]:
        part_number = part_url["part_number"]
        # Create actual content for each part (must be at least 5MB for all but the last part)
        content = f"Part {part_number} content - ".encode() * (part_size // 20)
        
        # Upload the part directly with the S3 client (in a real scenario, the presigned URL would be used)
        response = mock_s3.upload_part(
            Bucket=TEST_BUCKET_NAME,
            Key=s3_key,
            UploadId=upload_id,
            PartNumber=part_number,
            Body=content
        )
        
        parts.append({
            "part_number": part_number,
            "etag": response["ETag"]
        })
    
    # Step 4: Complete the multipart upload
    complete_result = mock_upload_service.complete_multipart_upload(
        s3_key=s3_key,
        upload_id=upload_id,
        parts=parts
    )
    
    assert complete_result["success"] is True, "Completing multipart upload should succeed"
    
    # Step 5: Verify the file was uploaded correctly
    verify_result = mock_upload_service.mark_upload_complete(s3_key)
    assert verify_result["success"] is True, "Verification should succeed"
    assert verify_result["exists"] is True, "File should exist in S3" 