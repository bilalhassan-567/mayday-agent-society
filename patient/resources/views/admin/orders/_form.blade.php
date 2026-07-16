    <div class="form-row">
        <label for="customer">Customer</label>
        <input id="customer" name="customer" value="{{ old('customer', $order->customer) }}" required>
        @error('customer') <div class="form-error">{{ $message }}</div> @enderror
    </div>
    <div class="form-row">
        <label for="item">Item</label>
        <input id="item" name="item" value="{{ old('item', $order->item) }}" required>
        @error('item') <div class="form-error">{{ $message }}</div> @enderror
    </div>
    <div class="form-row">
        <label for="amount">Amount (USD)</label>
        <input id="amount" name="amount" type="number" step="0.01" min="0"
               value="{{ old('amount', $order->exists ? number_format($order->amount_cents / 100, 2, '.', '') : '') }}" required>
        @error('amount') <div class="form-error">{{ $message }}</div> @enderror
    </div>
    <div class="form-row">
        <label for="status">Status</label>
        <select id="status" name="status">
            @foreach ($statuses as $s)
                <option value="{{ $s }}" @selected(old('status', $order->status) === $s)>{{ ucfirst($s) }}</option>
            @endforeach
        </select>
        @error('status') <div class="form-error">{{ $message }}</div> @enderror
    </div>
