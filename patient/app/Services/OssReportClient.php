<?php

namespace App\Services;

use App\Support\Settings;
use RuntimeException;

/**
 * Uploads generated reports to object storage. It authenticates with an access
 * key read from REAL config. The `env_key_corrupted` fault replaces that key
 * with an invalid one, so authentication genuinely fails — the same way the
 * real Alibaba Cloud OSS SDK (oss2) rejects a bad AccessKey in production.
 *
 * Prod mapping: on the Alibaba Cloud box this is backed by agents/alibaba_oss.py
 * (oss2). Here we validate/reject locally so the fault is reproducible offline.
 */
class OssReportClient
{
    public function upload(string $objectName, string $body): string
    {
        $key = (string) Settings::get(Settings::OSS_API_KEY, '');

        if (! $this->keyLooksValid($key)) {
            throw new RuntimeException(
                'OSS authentication failed: InvalidAccessKeyId — the provided access key is not valid'
            );
        }

        // Success path (real upload happens on the server via oss2).
        return "oss://mayday-reports/{$objectName}";
    }

    private function keyLooksValid(string $key): bool
    {
        // Valid Alibaba Cloud access keys start with "LTAI" and are long.
        return str_starts_with($key, 'LTAI') && strlen($key) >= 12;
    }
}
