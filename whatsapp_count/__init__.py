"""Counts what happens in a WhatsApp group export, on this laptop only.

    python -m whatsapp_count "C:\\Users\\me\\Documents\\group.txt"

Strictly local: no network, no AI model, standard library only. It prints
aggregates (how many messages, how many look like reports, how many name no
hotel or room, how many get no visible closing reply) and never a name, a
number, a message or a photo. It refuses to read a file that is inside this
repository, so that an export is never committed by mistake.

This folder imports nothing from the rest of the project.
"""
