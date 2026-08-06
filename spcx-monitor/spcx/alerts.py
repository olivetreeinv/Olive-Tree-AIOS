"""Alert dedupe + fan-out: SQLite log, UI broadcast, iMessage, optional Twilio SMS."""
import asyncio
import httpx

from . import config


class AlertManager:
    def __init__(self, store, broadcast, mode):
        self.store = store
        self.broadcast = broadcast
        self.mode = mode
        self.last = {}    # alert key -> last fire ts
        self.recent = []  # last 50 alerts, replayed to new UI clients

    async def fire(self, key, kind, ts, price, score, inputs, message,
                   sms=False, cooldown=config.SIGNAL_COOLDOWN_SEC, once=False):
        """Returns True if the alert actually fired (not deduped)."""
        prev = self.last.get(key)
        if prev is not None and (once or ts - prev < cooldown):
            return False
        self.last[key] = ts
        self.store.log_signal(ts, kind, score, price, self.mode, inputs)
        evt = {"type": "alert", "kind": kind, "key": key, "ts": ts, "price": price,
               "score": None if score is None else round(score, 3),
               "message": message, "sms": sms}
        self.recent.append(evt)
        del self.recent[:-50]
        await self.broadcast(evt)
        if sms:
            await self._notify(message)
        return True

    async def _notify(self, body):
        # iMessage via osascript (Mac, instant, free) — preferred
        if config.IMESSAGE_TO:
            await self._imessage(body)
        elif config.TWILIO_ACCOUNT_SID:
            await self._sms(body)

    async def _imessage(self, body):
        script = (
            'tell application "Messages"\n'
            f'  set t to first service whose service type = iMessage\n'
            f'  set b to buddy "{config.IMESSAGE_TO}" of t\n'
            f'  send "{body}" to b\n'
            'end tell'
        )
        try:
            proc = await asyncio.create_subprocess_exec(
                "osascript", "-e", script,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE)
            _, err = await asyncio.wait_for(proc.communicate(), timeout=10)
            if proc.returncode != 0:
                print(f"[alerts] iMessage failed: {err.decode().strip()}")
        except Exception as e:
            print(f"[alerts] iMessage error: {e}")

    async def _sms(self, body):
        sid, tok = config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN
        if not (sid and tok and config.TWILIO_FROM and config.TWILIO_TO):
            return
        url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
        try:
            async with httpx.AsyncClient(timeout=10) as cl:
                r = await cl.post(url, auth=(sid, tok),
                                  data={"From": config.TWILIO_FROM,
                                        "To": config.TWILIO_TO, "Body": body})
                r.raise_for_status()
        except Exception as e:
            print(f"[alerts] SMS failed: {e}")
