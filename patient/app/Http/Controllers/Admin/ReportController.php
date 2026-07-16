<?php

namespace App\Http\Controllers\Admin;

use App\Http\Controllers\Controller;
use App\Models\Order;
use App\Services\OssReportClient;
use App\Support\PatientLog;
use Illuminate\View\View;
use Throwable;

class ReportController extends Controller
{
    public function index(OssReportClient $oss): View
    {
        // Real dependency: the report is uploaded to object storage, so the
        // corrupted-OSS-key fault breaks THIS page, visibly.
        $orders = Order::query()->get();
        $report = [
            'generated_at' => now()->toIso8601String(),
            'order_count'  => $orders->count(),
            'gross_cents'  => (int) $orders->sum('amount_cents'),
        ];

        try {
            $uri = $oss->upload('report-'.now()->format('Ymd-His').'.json', json_encode($report));
        } catch (Throwable $e) {
            PatientLog::error('/admin/report', 'report upload failed', ['reason' => $e->getMessage()]);
            abort(500, 'Could not upload the report to object storage.');
        }

        return view('admin.report', ['report' => $report, 'uri' => $uri]);
    }
}
