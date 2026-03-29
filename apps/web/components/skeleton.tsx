import { cn } from "@/lib/cn";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded bg-zinc-800/60", className)} />;
}

// ── Pre-built skeleton compositions ─────────────────────────────

export function GlobalBarSkeleton() {
  return (
    <div className="grid grid-cols-9 gap-px bg-zinc-800/30 rounded-lg overflow-hidden border border-zinc-800/50">
      {Array.from({ length: 9 }).map((_, i) => (
        <div key={i} className="bg-[#0d0d12] px-3 py-2 space-y-1.5">
          <Skeleton className="h-2.5 w-12 mx-auto" />
          <Skeleton className="h-3.5 w-16 mx-auto" />
        </div>
      ))}
    </div>
  );
}

export function NseBarSkeleton() {
  return (
    <div className="grid grid-cols-6 gap-px bg-zinc-800/30 rounded-lg overflow-hidden border border-zinc-800/50">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="bg-[#0d0d12] px-3 py-2 space-y-1.5">
          <Skeleton className="h-2.5 w-14 mx-auto" />
          <Skeleton className="h-3.5 w-12 mx-auto" />
        </div>
      ))}
    </div>
  );
}

export function CardSkeleton() {
  return (
    <div className="rounded-xl border border-zinc-800/50 bg-[#0c0c11] overflow-hidden">
      <div className="h-0.5 bg-zinc-800/50" />
      <div className="p-3.5 space-y-3">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Skeleton className="h-4 w-4 rounded" />
            <Skeleton className="h-4 w-20" />
            <Skeleton className="h-3 w-16" />
          </div>
          <Skeleton className="h-5 w-14 rounded" />
        </div>
        {/* Price row */}
        <div className="flex items-end justify-between">
          <div className="space-y-1.5">
            <Skeleton className="h-7 w-28" />
            <Skeleton className="h-4 w-20" />
          </div>
          <div className="space-y-1.5 flex flex-col items-end">
            <Skeleton className="h-6 w-16" />
            <Skeleton className="h-3 w-20" />
          </div>
        </div>
        {/* Score bar */}
        <Skeleton className="h-1.5 w-full rounded-full" />
        {/* Reasons */}
        <div className="space-y-1">
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-4/5" />
          <Skeleton className="h-3 w-3/5" />
        </div>
        {/* Metrics grid */}
        <div className="grid grid-cols-6 gap-px bg-zinc-800/30 rounded overflow-hidden">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="bg-[#0a0a0f] py-1.5 px-1 space-y-1">
              <Skeleton className="h-2 w-8 mx-auto" />
              <Skeleton className="h-3 w-10 mx-auto" />
            </div>
          ))}
        </div>
        {/* Returns */}
        <div className="flex gap-3">
          <Skeleton className="h-3 w-16" />
          <Skeleton className="h-3 w-16" />
          <Skeleton className="h-3 w-16" />
          <Skeleton className="h-3 w-20 ml-auto" />
        </div>
      </div>
    </div>
  );
}

export function CardGridSkeleton() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
      {Array.from({ length: 4 }).map((_, i) => (
        <CardSkeleton key={i} />
      ))}
    </div>
  );
}

export function ActivitySkeleton() {
  return (
    <div className="rounded-xl border border-zinc-800/50 bg-[#0c0c11] overflow-hidden">
      <div className="px-4 py-2 border-b border-zinc-800/40 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Skeleton className="h-3.5 w-3.5 rounded" />
          <Skeleton className="h-3.5 w-32" />
        </div>
        <Skeleton className="h-3 w-12" />
      </div>
      <div className="space-y-0">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="px-4 py-2.5 border-b border-zinc-800/20 space-y-1.5">
            <div className="flex items-center gap-2">
              <Skeleton className="h-3.5 w-3.5 rounded-full" />
              <Skeleton className="h-3 w-16" />
              <Skeleton className="h-3 w-8" />
              <Skeleton className="h-4 w-16 rounded" />
              <Skeleton className="h-3 w-10 ml-auto" />
            </div>
            <div className="flex gap-4 ml-6">
              <Skeleton className="h-3 w-24" />
              <Skeleton className="h-3 w-24" />
              <Skeleton className="h-3 w-24" />
              <Skeleton className="h-3 w-24" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function HistorySkeleton() {
  return (
    <div className="rounded-xl border border-zinc-800/50 bg-[#0c0c11] overflow-hidden">
      <div className="px-4 py-2 border-b border-zinc-800/40 flex items-center gap-2">
        <Skeleton className="h-3.5 w-3.5 rounded" />
        <Skeleton className="h-3.5 w-28" />
        <Skeleton className="h-3 w-16 ml-auto" />
      </div>
      <div className="p-3 space-y-2">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="flex gap-4">
            <Skeleton className="h-3.5 w-16" />
            <Skeleton className="h-3.5 w-14" />
            <Skeleton className="h-3.5 w-14" />
            <Skeleton className="h-3.5 w-14" />
            <Skeleton className="h-3.5 w-14" />
          </div>
        ))}
      </div>
    </div>
  );
}

export function SystemInfoSkeleton() {
  return (
    <div className="rounded-xl border border-zinc-800/50 bg-[#0c0c11] p-4 space-y-3">
      <Skeleton className="h-3.5 w-24" />
      <div className="grid grid-cols-2 gap-x-6 gap-y-2">
        {Array.from({ length: 10 }).map((_, i) => (
          <div key={i} className="flex justify-between">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="h-3 w-10" />
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Cycle detail page skeleton ──────────────────────────────────

export function CycleDetailSkeleton() {
  return (
    <div className="max-w-[1600px] mx-auto px-5 py-4 space-y-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="rounded-xl border border-zinc-800/50 bg-[#0c0c11] overflow-hidden">
          <div className="h-0.5 bg-zinc-800/50" />
          {/* Header */}
          <div className="px-5 py-3 border-b border-zinc-800/30 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Skeleton className="h-5 w-5 rounded" />
              <Skeleton className="h-5 w-24" />
              <Skeleton className="h-4 w-20" />
            </div>
            <div className="flex items-center gap-4">
              <Skeleton className="h-6 w-20" />
              <Skeleton className="h-5 w-16" />
              <Skeleton className="h-6 w-40 rounded" />
            </div>
          </div>
          {/* Reasons */}
          <div className="px-5 py-2 border-b border-zinc-800/20 flex gap-2">
            <Skeleton className="h-5 w-48 rounded-full" />
            <Skeleton className="h-5 w-36 rounded-full" />
            <Skeleton className="h-5 w-40 rounded-full" />
          </div>
          {/* Market data */}
          <div className="px-5 py-2 border-b border-zinc-800/20 space-y-2">
            <Skeleton className="h-2.5 w-20" />
            <div className="grid grid-cols-8 gap-2">
              {Array.from({ length: 8 }).map((_, j) => (
                <div key={j} className="space-y-1">
                  <Skeleton className="h-2 w-12" />
                  <Skeleton className="h-3.5 w-16" />
                </div>
              ))}
            </div>
          </div>
          {/* Signals grid */}
          <div className="px-5 py-2 space-y-2">
            <Skeleton className="h-2.5 w-28" />
            <div className="grid grid-cols-5 gap-x-4 gap-y-1.5">
              {Array.from({ length: 20 }).map((_, j) => (
                <div key={j} className="flex justify-between">
                  <Skeleton className="h-3 w-24" />
                  <Skeleton className="h-3 w-14" />
                </div>
              ))}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
