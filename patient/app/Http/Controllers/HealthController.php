<?php

namespace App\Http\Controllers;

use App\Support\HealthProbes;
use App\Support\PatientLog;
use Illuminate\Http\JsonResponse;

class HealthController extends Controller
{
    public function show(): JsonResponse
    {
        $result = HealthProbes::run();
        $status = $result['healthy'] ? 200 : 503;

        if ($result['healthy']) {
            PatientLog::info('/health', 'all dependencies healthy');
        } else {
            $sick = collect($result['checks'])
                ->filter(fn ($c) => ! $c['ok'])
                ->map(fn ($c, $k) => "$k: {$c['detail']}")
                ->values()->all();
            PatientLog::error('/health', 'dependency check failed', ['failing' => $sick]);
        }

        return response()->json([
            'status' => $result['healthy'] ? 'ok' : 'sick',
            'checks' => $result['checks'],
        ], $status);
    }
}
