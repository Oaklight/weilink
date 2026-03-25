"""Multi-session echo bot — echoes messages from all sessions."""

import sys
import time

sys.path.insert(0, "src")

from weilink import WeiLink

wl = WeiLink()

# Load all three sessions
wl.login(name="屁屁")
wl.login(name="zb")

print(f"Sessions: {wl.sessions}")
print(f"Bot IDs: {wl.bot_ids}")
print("Listening for messages on all sessions... (Ctrl+C to stop)\n")

try:
    while True:
        try:
            msgs = wl.recv(timeout=35.0)
        except Exception as e:
            print(f"recv error: {e}")
            time.sleep(2)
            continue

        for msg in msgs:
            print(
                f"[{msg.bot_id}] {msg.from_user}: "
                f"{msg.text or f'<{msg.msg_type.name}>'}"
            )
            # Echo back
            reply = (
                f"[echo] {msg.text}"
                if msg.text
                else f"[echo] received {msg.msg_type.name}"
            )
            ok = wl.send(msg.from_user, reply)
            print(f"  -> reply {'OK' if ok else 'FAILED'}")

except KeyboardInterrupt:
    print("\nStopping...")
    wl.close()
