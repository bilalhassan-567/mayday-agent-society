<?php

namespace App\Http\Controllers;

use Illuminate\Http\JsonResponse;
use Illuminate\Support\Facades\Route as RouteFacade;

/**
 * Watch-target discovery for the Watchman.
 *
 * The Watchman patrols the WHOLE patient system, not a hardcoded
 * subset. Instead of maintaining a list in two places, it fetches this endpoint
 * on startup and patrols every route the app actually exposes — so any page
 * added later is watched automatically.
 *
 * Each target carries its EXPECTED healthy status code (a guarded page correctly
 * 302s to /login when unauthenticated; the root redirects) so the Watchman only
 * alarms on a genuine deviation, never on an expected redirect.
 */
class WatchController extends Controller
{
    /** Paths whose healthy response is a redirect, not a 200. */
    private const REDIRECT_OVERRIDES = ['/' => 302];

    /** The console pages a fault visibly breaks — a fault here is a real incident. */
    private const CRITICAL = ['/dashboard', '/admin/users', '/admin/orders', '/admin/report', '/admin/users/1/edit', '/health'];

    /**
     * Concrete deep-link canaries the Watchman must patrol even though their route
     * is parameterised (auto-discovery below skips `{...}` routes). The user-edit
     * form is where the route_renamed fault surfaces, so it must be watched.
     */
    private const EXTRA = ['/admin/users/1/edit' => ['expect' => 200, 'auth' => true]];

    public function targets(): JsonResponse
    {
        $seen = [];

        foreach (RouteFacade::getRoutes() as $route) {
            if (! in_array('GET', $route->methods(), true)) {
                continue;                      // Watchman does GET patrols only
            }

            $path = '/'.ltrim($route->uri(), '/');

            if (str_contains($path, '{')) {
                continue;                      // needs parameters — not generically patrollable
            }
            if ($path === '/_watch/targets') {
                continue;                      // don't watch the watch endpoint itself
            }

            // Expected status for the Watchman, which patrols AUTHENTICATED (a
            // monitoring service account). Auth pages -> 200; guest-only pages
            // (login) redirect an authenticated visitor -> 302; '/' redirects.
            $middleware = $route->middleware();
            $authRequired = in_array('auth', $middleware, true);
            $expect = 200;
            if (in_array('guest', $middleware, true)) {
                $expect = 302;
            }
            if (isset(self::REDIRECT_OVERRIDES[$path])) {
                $expect = self::REDIRECT_OVERRIDES[$path];
            }

            $seen[$path] = [
                'path'     => $path,
                'expect'   => $expect,
                'auth'     => $authRequired,
                'critical' => in_array($path, self::CRITICAL, true),
            ];
        }

        // Add the explicit deep-link canaries (parameterised routes the loop skips).
        foreach (self::EXTRA as $path => $meta) {
            $seen[$path] = [
                'path'     => $path,
                'expect'   => $meta['expect'],
                'auth'     => $meta['auth'],
                'critical' => in_array($path, self::CRITICAL, true),
            ];
        }

        // Critical pages first, then alphabetical — stable order for the log.
        $targets = array_values($seen);
        usort($targets, fn ($a, $b) => [$b['critical'], $a['path']] <=> [$a['critical'], $b['path']]);

        return response()->json([
            'base_url'         => url('/'),
            'interval_seconds' => 5,
            'fail_threshold'   => 2,
            'login_url'        => '/login',
            'count'            => count($targets),
            'targets'          => $targets,
        ]);
    }
}
