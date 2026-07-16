<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;

/**
 * Injector's private ledger. NOT for use by patient routes or the AI doctor.
 * See the golden rule in the create_faults_table migration.
 */
#[Fillable([
    'fault_key', 'kind', 'target_setting', 'target_file', 'bad_value', 'original_value',
    'status', 'injected_at', 'cleared_at',
])]
class Fault extends Model
{
    protected function casts(): array
    {
        return [
            'injected_at' => 'datetime',
            'cleared_at' => 'datetime',
        ];
    }
}
