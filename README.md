# Transformer Client Live

Desktop client in Python for:
- login to backend with `rawPassword`
- bearer auth with refresh after `401`
- downloading transformer/meter/register configuration
- grouping meters by `serialPort`
- reading Modbus RTU locally and showing live values in UI
- local target/threshold control for one active register at a time
- motor driving through system commands configured in `client-config.json`

## Run

```bash
python3 main.py
```

Optional:

```bash
python3 -m pip install -r requirements.txt
```

## Notes

- Local configuration is loaded from `client-config.json`, with fallback to `resources/client-config.default.json`.
- `register-control.json` stores local `targetValue` and `thresholdValue` per register. Only one register can be active for motor control at a time.
- Motor control runs locally from live register value and executes `motorForwardCommand`, `motorReverseCommand` and `motorStopCommand`.
- One Modbus RTU session is created per serial port, exactly as required by the spec.
- On Raspberry Pi / Linux the serial transport works without `pip`, using `termios` from Python standard library.
- `pyserial` remains optional and can still be used when available.
