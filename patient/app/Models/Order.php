<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;

#[Fillable(['customer', 'item', 'amount_cents', 'status'])]
class Order extends Model
{
    //
}
