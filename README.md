# Transformer Client Live

Desktop client in Python for:
- login to backend with `rawPassword`
- bearer auth with refresh after `401`
- downloading transformer/meter/register configuration
- grouping meters by `serialPort`
- reading Modbus RTU locally and showing live values in UI
- local target/threshold control for one active register at a time
- motor driving through system commands configured in `client-config.json`
- websocket metrics publishing to `/ws/transformers/{transformerId}/metrics?token=<accessToken>`

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
- The active register remains selected when the target is reached; corrections resume whenever the value leaves the threshold range. Missing or stale measurements pause movement until fresh readings return, without clearing the selection. Use **Stop control** to end regulation; restarting the app also requires manual activation.
- If the selected register temporarily disappears from the backend configuration, regulation waits for that same register and fresh readings to return. It does not switch to another register or require reactivation.
- The repo now includes `DRV8825` helper scripts for `EN=GPIO22`, `STEP=GPIO27`, `DIR=GPIO17` using `pinctrl`.
- If `M0/M1/M2` are wired, set `motorM0Pin`, `motorM1Pin`, `motorM2Pin` and `motorMicrostepMode` in `client-config.json` for smoother NEMA17 motion.
- One Modbus RTU session is created per serial port, exactly as required by the spec.
- On Raspberry Pi / Linux the serial transport works without `pip`, using `termios` from Python standard library.
- `pyserial` remains optional and can still be used when available.
