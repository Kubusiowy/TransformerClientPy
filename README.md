# Transformer Client Live

Desktop client in Python for:
- login to backend with `rawPassword`
- bearer auth with refresh after `401`
- downloading transformer/meter/register configuration
- grouping meters by `serialPort`
- reading Modbus RTU locally and showing live values in UI

## Run

```bash
python3 -m pip install -r requirements.txt
python3 main.py
```

## Notes

- Local configuration is loaded from `client-config.json`, with fallback to `resources/client-config.default.json`.
- The current version does not control motors, save thresholds or send metrics back to backend.
- One Modbus RTU session is created per serial port, exactly as required by the spec.
