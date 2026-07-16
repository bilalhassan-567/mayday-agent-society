<?php

namespace App\Console\Commands;

use App\Support\FaultInjector;
use Illuminate\Console\Command;

class FaultClear extends Command
{
    protected $signature = 'fault:clear {key? : Fault key to clear; omit to clear all active faults}';

    protected $description = 'Injector reset: restore the real config a fault corrupted (dev/test only, NOT the doctor\'s fix).';

    public function handle(): int
    {
        $restored = FaultInjector::clear($this->argument('key'));

        if (empty($restored)) {
            $this->info('No active faults to clear.');

            return self::SUCCESS;
        }

        foreach ($restored as $r) {
            $this->info("Cleared '{$r['fault_key']}' — {$r['setting']} restored to '{$r['restored_to']}'.");
        }

        return self::SUCCESS;
    }
}
