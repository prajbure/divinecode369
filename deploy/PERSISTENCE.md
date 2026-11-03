# Persistent platform data

The current Render blueprint is retained. No paid service, disk or database has been created.

Before treating synchronized watchlists, alert rules, device approvals or login sessions as durable, attach an owner-approved persistent volume to the existing backend. Render documents that its default filesystem is ephemeral and only files beneath a persistent mount survive replacement: [Render persistent disks](https://render.com/docs/disks).

For an existing approved mount at `/var/data/divine`, the concrete non-secret configuration is:

```text
PLATFORM_DATABASE_PATH=/var/data/divine/private/platform.sqlite3
```

The directory is created privately at runtime. This database contains user-owned preferences, alert rules/inbox records and **hashed** mobile credentials. Provider quotes are not written to it. Do not populate this mount by enabling historical retention or model training.

If the owner also wants existing market/application storage moved, configure the existing `DATABASE_PATH` separately and migrate it with a controlled backup while the writer is stopped. Its `.private` sibling contains the existing admin session database and Kite vault. Preserve the backend encryption configuration when migrating a vault. Do not copy active SQLite files while transactions are running; use SQLite's backup API or stop the writer first.

After a mount change, verify ownership/permissions, create a test saved item and rule, restart the service, and confirm both survive. Also verify owner login, device renewal/revocation and official Kite reauthentication. No persistence-through-redeployment test has been performed on the live service because no persistent volume was authorized or configured in this task.

Until then, Room/browser records are local copies, not a guarantee of durable server synchronization. A backend replacement may require owner/device reauthentication and can lose server-side personal records. A hosting-plan change needs the owner's approval; this document does not apply one automatically.
