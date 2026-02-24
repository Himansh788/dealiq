import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { SheetDescription } from "@/components/ui/sheet";
import { Clock } from "lucide-react";
import HealthBreakdown from "./deal/HealthBreakdown";
import AckSection from "./deal/AckSection";
import MismatchChecker from "./deal/MismatchChecker";
import DealTimeline from "./deal/DealTimeline";

interface Props {
  dealId: string | null;
  dealName: string;
  repName?: string;
  onClose: () => void;
}

export default function DealDetailPanel({ dealId, dealName, repName, onClose }: Props) {
  return (
    <Sheet open={!!dealId} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="w-full overflow-y-auto border-border/50 bg-background sm:max-w-2xl">
        <SheetHeader className="pb-4">
          <SheetTitle className="text-xl text-foreground">{dealName || "Deal Analysis"}</SheetTitle>
          <SheetDescription className="text-muted-foreground">In-depth deal intelligence and actions</SheetDescription>
        </SheetHeader>

        {dealId && (
          <Accordion type="multiple" defaultValue={["timeline", "health", "ack", "mismatch"]} className="space-y-2">

            <AccordionItem value="timeline" className="rounded-lg border border-border/50 px-4">
              <AccordionTrigger className="text-foreground hover:no-underline">
                <div className="flex items-center gap-2">
                  <Clock className="h-4 w-4 text-primary" />
                  Deal Timeline
                </div>
              </AccordionTrigger>
              <AccordionContent>
                <DealTimeline dealId={dealId} />
              </AccordionContent>
            </AccordionItem>

            <AccordionItem value="health" className="rounded-lg border border-border/50 px-4">
              <AccordionTrigger className="text-foreground hover:no-underline">
                Health Score Breakdown
              </AccordionTrigger>
              <AccordionContent>
                <HealthBreakdown dealId={dealId} />
              </AccordionContent>
            </AccordionItem>

            <AccordionItem value="ack" className="rounded-lg border border-border/50 px-4">
              <AccordionTrigger className="text-foreground hover:no-underline">
                Advance / Close / Kill
              </AccordionTrigger>
              <AccordionContent>
                <AckSection dealId={dealId} />
              </AccordionContent>
            </AccordionItem>

            <AccordionItem value="mismatch" className="rounded-lg border border-border/50 px-4">
              <AccordionTrigger className="text-foreground hover:no-underline">
                Narrative Mismatch Checker
              </AccordionTrigger>
              <AccordionContent>
                <MismatchChecker dealId={dealId} />
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        )}
      </SheetContent>
    </Sheet>
  );
}
