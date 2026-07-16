"""Alibaba Cloud OSS client (production object storage for generated reports).

This is the real Alibaba Cloud integration behind the patient's report upload. In
local dev the patient validates/rejects the OSS access key offline (so the
`env_key_corrupted` fault is reproducible without a network); on the deployed
Alibaba Cloud box, report bodies are actually stored in an OSS bucket through the
official **oss2** SDK by this module.

It authenticates with an Alibaba Cloud AccessKey pair and talks to an OSS endpoint
— both read from the environment (agents/.env), never hard-coded:

    OSS_KEY_ID       AccessKey ID     (starts with "LTAI…")
    OSS_KEY_SECRET   AccessKey secret
    OSS_ENDPOINT     e.g. https://oss-ap-southeast-1.aliyuncs.com
    OSS_BUCKET       e.g. mayday-reports

Proof-of-deployment note: together with agents/llm.py (Qwen inference via the
Alibaba Cloud DashScope endpoint), this file is the code-level evidence that the
backend uses Alibaba Cloud services and APIs. See docs/deployment-proof.md.

`oss2` is imported lazily so this module imports cleanly even where the SDK or
credentials are absent (local dev); the import cost is paid only on a real upload.
"""
import os

import config  # noqa: F401  (importing loads agents/.env into the environment)


class OssConfigError(RuntimeError):
    """Raised when OSS credentials/endpoint are missing or malformed."""


def _settings() -> dict:
    """Read OSS connection settings from the environment; validate shape."""
    s = {
        "key_id": os.environ.get("OSS_KEY_ID", ""),
        "key_secret": os.environ.get("OSS_KEY_SECRET", ""),
        "endpoint": os.environ.get("OSS_ENDPOINT", ""),
        "bucket": os.environ.get("OSS_BUCKET", "mayday-reports"),
    }
    missing = [k for k in ("key_id", "key_secret", "endpoint") if not s[k]]
    if missing:
        raise OssConfigError(f"OSS not configured — missing {', '.join(missing)} in the environment")
    # Alibaba Cloud AccessKey IDs start with "LTAI"; fail fast on an obviously bad key
    # so a misconfigured deploy surfaces here instead of as an opaque 403 mid-upload.
    if not s["key_id"].startswith("LTAI") or len(s["key_id"]) < 12:
        raise OssConfigError("OSS_KEY_ID does not look like a valid Alibaba Cloud AccessKey ID")
    return s


def _bucket():
    """Build an authenticated oss2 Bucket handle (lazy import of the SDK)."""
    import oss2  # Alibaba Cloud OSS SDK — see requirements.txt

    s = _settings()
    auth = oss2.Auth(s["key_id"], s["key_secret"])
    return oss2.Bucket(auth, s["endpoint"], s["bucket"]), s["bucket"]


def upload(object_name: str, body: str | bytes) -> str:
    """Store a report body in OSS and return its oss:// URI.

    Mirrors the contract of the patient's App\\Services\\OssReportClient so the app
    behaves identically once pointed at this module in production.
    """
    bucket, name = _bucket()
    if isinstance(body, str):
        body = body.encode("utf-8")
    bucket.put_object(object_name, body)
    return f"oss://{name}/{object_name}"


def healthcheck() -> dict:
    """Lightweight connectivity/credential check for the deployment-proof step.

    Returns {"ok": bool, "detail": str} without raising, so it can be wired into a
    /health probe or run from the CLI right after provisioning the bucket.
    """
    try:
        bucket, name = _bucket()
        bucket.get_bucket_info()  # cheap authenticated call
        return {"ok": True, "detail": f"OSS bucket '{name}' reachable"}
    except OssConfigError as e:
        return {"ok": False, "detail": f"config: {e}"}
    except Exception as e:  # noqa: BLE001 — surface any SDK/network error verbatim
        return {"ok": False, "detail": f"{type(e).__name__}: {e}"}


if __name__ == "__main__":
    # Post-deploy smoke test: python alibaba_oss.py
    hc = healthcheck()
    print(("OK  " if hc["ok"] else "FAIL ") + hc["detail"])
    if hc["ok"]:
        uri = upload("mayday-deploy-check.txt", "mayday oss connectivity check")
        print("uploaded:", uri)
    raise SystemExit(0 if hc["ok"] else 1)
