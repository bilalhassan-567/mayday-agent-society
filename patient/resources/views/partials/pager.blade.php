@if ($paginator->hasPages())
    <div class="pager">
        @if ($paginator->onFirstPage())
            <span class="pg disabled">← Prev</span>
        @else
            <a class="pg" href="{{ $paginator->previousPageUrl() }}">← Prev</a>
        @endif

        <span class="pg-info">Page {{ $paginator->currentPage() }} of {{ $paginator->lastPage() }}</span>

        @if ($paginator->hasMorePages())
            <a class="pg" href="{{ $paginator->nextPageUrl() }}">Next →</a>
        @else
            <span class="pg disabled">Next →</span>
        @endif
    </div>
@endif
