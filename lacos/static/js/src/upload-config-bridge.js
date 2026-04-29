(function () {
  const defaults = {
    chunkSize: 100 * 1024 * 1024,
    maxConcurrent: 8,
    partUploadConcurrency: 6,
    multipartThreshold: 5 * 1024 * 1024 * 1024,
    thresholdLabel: "5 GB",
    maxRetries: 3,
    retryDelayBase: 0.5,
  };

  const existing = window.UPLOAD_CONFIG || {};
  let serverConfig = {};
  const configNode = document.getElementById("upload-config-data");

  if (configNode) {
    try {
      serverConfig = JSON.parse(configNode.textContent) || {};
    } catch (error) {
      console.warn("Failed to parse upload config JSON:", error);
    }
    configNode.remove();
  }

  const resolved = {
    chunkSize:
      serverConfig.chunk_size ||
      existing.chunkSize ||
      existing.chunk_size ||
      defaults.chunkSize,
    maxConcurrent:
      serverConfig.max_concurrency ||
      existing.maxConcurrent ||
      existing.max_concurrency ||
      defaults.maxConcurrent,
    partUploadConcurrency:
      serverConfig.part_upload_concurrency ||
      existing.partUploadConcurrency ||
      existing.part_upload_concurrency ||
      defaults.partUploadConcurrency,
    multipartThreshold:
      serverConfig.multipart_threshold ||
      existing.multipartThreshold ||
      existing.multipart_threshold ||
      defaults.multipartThreshold,
    thresholdLabel:
      serverConfig.multipart_threshold_label ||
      existing.multipartThresholdLabel ||
      existing.multipart_threshold_label ||
      defaults.thresholdLabel,
    maxRetries:
      serverConfig.max_retries ||
      existing.maxRetries ||
      existing.max_retries ||
      defaults.maxRetries,
    retryDelayBase:
      serverConfig.retry_delay_base ||
      existing.retryDelayBase ||
      existing.retry_delay_base ||
      defaults.retryDelayBase,
  };

  window.UPLOAD_CONFIG = Object.assign({}, existing, {
    chunkSize: resolved.chunkSize,
    chunk_size: resolved.chunkSize,
    maxConcurrent: resolved.maxConcurrent,
    max_concurrency: resolved.maxConcurrent,
    partUploadConcurrency: resolved.partUploadConcurrency,
    part_upload_concurrency: resolved.partUploadConcurrency,
    multipartThreshold: resolved.multipartThreshold,
    multipart_threshold: resolved.multipartThreshold,
    multipartThresholdLabel: resolved.thresholdLabel,
    multipart_threshold_label: resolved.thresholdLabel,
    maxRetries: resolved.maxRetries,
    max_retries: resolved.maxRetries,
    retryDelayBase: resolved.retryDelayBase,
    retry_delay_base: resolved.retryDelayBase,
  });

  window.S3_UPLOAD_CHUNK_SIZE = window.UPLOAD_CONFIG.chunkSize;
  window.S3_UPLOAD_MAX_CONCURRENT = window.UPLOAD_CONFIG.maxConcurrent;
  window.S3_MULTIPART_THRESHOLD = window.UPLOAD_CONFIG.multipartThreshold;
  window.MULTIPART_THRESHOLD = window.UPLOAD_CONFIG.multipartThreshold;
  window.MULTIPART_THRESHOLD_LABEL = window.UPLOAD_CONFIG.multipartThresholdLabel;
  window.UploadConfig = window.UPLOAD_CONFIG;
  window.uploadConfig = window.UPLOAD_CONFIG;
})();
