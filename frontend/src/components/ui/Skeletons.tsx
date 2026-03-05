import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";

export function MetricCardSkeleton() {
    return (
        <Card className="group relative overflow-hidden bg-card/60 border-border/40">
            <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/50 to-transparent" />
            <CardContent className="flex items-center gap-4 p-5">
                <div className="skeleton h-11 w-11 shrink-0 rounded-xl" />
                <div className="space-y-2 flex-1">
                    <div className="skeleton h-3 w-20 rounded" />
                    <div className="skeleton h-8 w-24 rounded" />
                    <div className="skeleton h-3 w-32 rounded" />
                </div>
            </CardContent>
        </Card>
    );
}

export function TableRowSkeleton() {
    return (
        <div className="flex items-center justify-between p-4 border-b border-border/20">
            <div className="flex items-center gap-4 flex-1">
                <div className="skeleton h-10 w-10 shrink-0 rounded-lg" />
                <div className="space-y-2 max-w-[200px] w-full">
                    <div className="skeleton h-4 w-full rounded" />
                    <div className="skeleton h-3 w-3/4 rounded" />
                </div>
            </div>
            <div className="skeleton h-6 w-24 rounded mx-4" />
            <div className="flex gap-4 items-center">
                <div className="skeleton h-8 w-20 rounded" />
                <div className="skeleton h-8 w-16 rounded-full mx-4" />
            </div>
        </div>
    );
}

export function GaugeSkeleton() {
    return (
        <div className="flex flex-col items-center gap-2">
            <div className="skeleton h-12 w-12 rounded-full" />
        </div>
    );
}
