# Datasets

This directory stores **trackable dataset manifests and small metadata**, not a mandatory copy of every payload.

Recommended shape:

```text
datasets/<name>/dataset.yaml
datasets/<name>/metadata/
```

Large payload/cache paths are ignored by the V3 Git policy and may live on external Storage Roots.
