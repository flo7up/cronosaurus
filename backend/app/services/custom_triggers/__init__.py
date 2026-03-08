"""
Custom triggers auto-discovery package.

Drop a Python file into this folder following the pattern in _template.py
and it will be automatically started as an event-driven trigger service
in Cronosaurus.

Files starting with _ (like _template.py) are ignored by the loader.

Note: Interval-based triggers already work out of the box — just enable
the built-in "triggers" tool on an agent.  This folder is for adding
new *event-driven* trigger types (e.g. watch a webhook, RSS feed, etc.).
"""
