"""LD2420 energy listener — uses the upstream LD2420Listener pattern.

Exposes 16 per-gate energy values to ESPHome. No upstream fork is needed;
the parent `ld2420` component already calls `on_energy()` on every parsed
energy frame.
"""