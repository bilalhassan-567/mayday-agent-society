# Route not found / renamed save route

Symptom: `/admin/users/{id}/edit` returns 500; the log shows
`[/admin/users/edit] save route could not be resolved` naming a route it looked
up. `/health` shows `routing` FAIL with "save route '<name>' is not defined".

Cause: the admin user-edit form resolves its POST target by name
(`edit_save_route`). Someone renamed the route (or the setting) so the referenced
name no longer exists and `route()` throws RouteNotFoundException.

Fix: restore `edit_save_route` to the registered route name (`admin.users.update`).
Confirm `/admin/users/1/edit` renders 200 and the routing health check passes.
