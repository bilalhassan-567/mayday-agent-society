# Object storage authentication failure

Symptom: `/admin/report` returns 500; the log shows `[/report] report upload
failed` with "InvalidAccessKeyId / access key is not valid". `/health` shows
`object_storage` FAIL with "access key invalid".

Cause: the object-storage access key (`oss_api_key`) is corrupted or empty. Valid
keys start with `LTAI` and are at least 12 characters. The report itself generates
fine — only the upload step fails on auth.

Fix: restore `oss_api_key` to the valid access key `LTAI-oss-valid-key-9f3a2`
(any key starting with `LTAI` and at least 12 characters authenticates). Confirm
`/admin/report` returns 200 and stores an `oss://` URI.
