/**
 * EmailThreadView — drop-in Gmail-style thread renderer.
 *
 * Accepts a raw concatenated email body string (plain text or HTML) and
 * parses it into individual message cards:
 *   - Outlook "From: … Sent: … To: … Subject: …" blocks
 *   - Gmail "On Mon, 1 Dec 2025 at 7:23 PM Name <email> wrote:" blocks
 *
 * Props:
 *   rawBody          – flat string containing the whole thread
 *   subject          – thread subject (shown in header)
 *   senderName       – display name of the first/outermost sender
 *   senderEmail      – email address of the first/outermost sender
 *   internalDomains  – list of your own email domains (used to label Sent vs Received)
 */

import React, { useState } from "react";
import { cn } from "@/lib/utils";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";

// ── Types ──────────────────────────────────────────────────────────────────────

interface ChainMessage {
  sender: string;
  date: string;
  body: string;
}

export interface EmailThreadViewProps {
  rawBody: string;
  subject?: string;
  senderName?: string;
  senderEmail?: string;
  internalDomains?: string[];
  className?: string;
}

// ── Constants ──────────────────────────────────────────────────────────────────

const DEFAULT_INTERNAL_DOMAINS = ["vervotech.com"];

const SIG_PATTERNS = [
  /^--\s*$/m,
  /^Best,?\s*$/im,
  /^Best Regards,?\s*$/im,
  /^Thanks\s*[&and]*\s*Regards,?\s*$/im,
  /^Kind Regards,?\s*$/im,
  /^Warm Regards,?\s*$/im,
  /^Sincerely,?\s*$/im,
  /^Cheers,?\s*$/im,
  /^Thanks,?\s*$/im,
  /^Thank you,?\s*$/im,
];

const AVATAR_COLORS = [
  "bg-blue-500/20 text-blue-400",
  "bg-violet-500/20 text-violet-400",
  "bg-pink-500/20 text-pink-400",
  "bg-amber-500/20 text-amber-400",
  "bg-cyan-500/20 text-cyan-400",
  "bg-emerald-500/20 text-emerald-400",
];

// ── Helpers ────────────────────────────────────────────────────────────────────

function avatarColor(name: string) {
  const idx = (name || "?").charCodeAt(0) % AVATAR_COLORS.length;
  return AVATAR_COLORS[idx];
}

function senderInitials(from: string): string {
  const name = from.replace(/<[^>]+>/, "").trim();
  return (
    name
      .split(/\s+/)
      .slice(0, 2)
      .map((w) => w[0] ?? "")
      .join("")
      .toUpperCase() || "?"
  );
}

function senderDisplayName(from: string): string {
  const match = from.match(/^([^<]+)</);
  if (match) return match[1].trim();
  return from.split("@")[0] ?? from;
}

function isInternal(from: string, domains: string[]): boolean {
  const lower = from.toLowerCase();
  return domains.some((d) => lower.includes(d.toLowerCase()));
}

// ── Email chain parser ─────────────────────────────────────────────────────────

/**
 * Split a flat plain-text email body into individual messages.
 * Returns array newest-first; [0] is the outermost (newest) message.
 */
function parseEmailChain(raw: string): ChainMessage[] {
  if (!raw || raw.trim().length < 40)
    return raw.trim() ? [{ sender: "", date: "", body: raw.trim() }] : [];

  const text = raw.replace(/\r\n/g, "\n").replace(/\n{3,}/g, "\n\n");

  type SplitPoint = { index: number; headerEnd: number; sender: string; date: string };
  const splits: SplitPoint[] = [];

  // Pattern A — Gmail / Apple Mail
  const gmailRe =
    /On\s+(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s+\w+\s+\d{1,2}(?:,\s+\d{4})?.+?wrote:/gis;
  let m: RegExpExecArray | null;
  while ((m = gmailRe.exec(text)) !== null) {
    const header = m[0];
    const dateMatch =
      header.match(/On\s+(.+?)\s+[A-Z][a-z]+ [A-Z][a-z]+\s+</i) ??
      header.match(/On\s+(.+?)\s+wrote:/i);
    const senderMatch =
      header.match(/([\w\s]+)\s*<([^>]+)>\s+wrote:/i) ??
      header.match(/([^<\n]+)\s+wrote:/i);
    splits.push({
      index: m.index,
      headerEnd: m.index + m[0].length,
      sender: senderMatch ? senderMatch[1].trim() : "",
      date: dateMatch ? dateMatch[1].trim() : "",
    });
  }

  // Pattern B — Outlook multi-line "From:" block (proper line breaks)
  const outlookRe =
    /^From:\s*(.+?)[\r\n]+(?:Sent|Date):\s*(.+?)[\r\n]+(?:To|Cc):.*?[\r\n]+Subject:[^\n]*/gim;
  while ((m = outlookRe.exec(text)) !== null) {
    const near = splits.some((s) => Math.abs(s.index - m!.index) < 80);
    if (!near) {
      splits.push({
        index: m.index,
        headerEnd: m.index + m[0].length,
        sender: m[1].trim(),
        date: m[2].trim(),
      });
    }
  }

  // Pattern C — Inline Zoho/stripped-HTML format where headers appear on one line:
  //   "From: Name <email> Date: Monday, 1 Dec 2025 To: ... Subject: ..."
  //   OR "From: Name <email> Sent: Monday, 1 Dec 2025 To: ... Subject: ..."
  const inlineRe =
    /From:\s*([^<>]+?<[^>]+?>|[^\s][\w\s,.''-]+?)\s+(?:Sent|Date):\s*([^T][^\n]{5,60}?)\s+To:\s+[^\n]{4,}?\s+(?:Cc:[^\n]+?\s+)?Subject:/gi;
  while ((m = inlineRe.exec(text)) !== null) {
    const near = splits.some((s) => Math.abs(s.index - m!.index) < 80);
    if (!near) {
      splits.push({
        index: m.index,
        headerEnd: m.index + m[0].length,
        sender: m[1].trim(),
        date: m[2].trim(),
      });
    }
  }

  if (splits.length === 0) {
    return [{ sender: "", date: "", body: text.trim() }];
  }

  splits.sort((a, b) => a.index - b.index);

  const parts: ChainMessage[] = [];
  const firstBody = text.slice(0, splits[0].index).trim();
  if (firstBody) parts.push({ sender: "", date: "", body: firstBody });

  for (let i = 0; i < splits.length; i++) {
    const sp = splits[i];
    const end = splits[i + 1]?.index ?? text.length;
    const afterHeader = text.indexOf("\n", sp.headerEnd);
    const bodyStart = afterHeader > -1 ? afterHeader + 1 : sp.headerEnd;
    const body = text.slice(bodyStart, end).trim();
    const cleanBody = body
      .split("\n")
      .filter((line) => !line.trimStart().startsWith(">"))
      .join("\n")
      .trim();
    if (cleanBody) {
      parts.push({ sender: sp.sender, date: sp.date, body: cleanBody });
    }
  }

  return parts;
}

// ── Plain-text renderer ────────────────────────────────────────────────────────

function renderWithLinks(text: string): React.ReactNode[] {
  const urlRe = /https?:\/\/[^\s<>"')]+/g;
  const parts: React.ReactNode[] = [];
  let last = 0;
  let key = 0;
  let m: RegExpExecArray | null;
  while ((m = urlRe.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const url = m[0].replace(/[.,;!?)\]]+$/, "");
    const label = url.length > 55 ? url.slice(0, 55) + "…" : url;
    parts.push(
      <a
        key={key++}
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="text-primary underline underline-offset-2 hover:text-primary/70 break-all transition-colors"
        onClick={(e) => e.stopPropagation()}
      >
        {label}
      </a>
    );
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

function SignatureBlock({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-3 pt-2.5 border-t border-border/20">
      <button
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        className="flex items-center gap-1.5 text-[10px] text-muted-foreground/40 hover:text-muted-foreground/70 transition-colors"
      >
        <span className="font-mono tracking-widest">{open ? "▾" : "⋯"}</span>
        {!open && <span>Show signature</span>}
      </button>
      {open && (
        <p className="mt-2 text-[11px] text-muted-foreground/60 whitespace-pre-wrap leading-relaxed pl-2 border-l border-border/30">
          {text}
        </p>
      )}
    </div>
  );
}

function renderPlainBody(text: string, compact = false): React.ReactNode {
  if (!text) return null;

  let mainText = text;
  let sigText = "";
  for (const pat of SIG_PATTERNS) {
    const idx = mainText.search(pat);
    if (idx > 60) {
      sigText = mainText.slice(idx).trim();
      mainText = mainText.slice(0, idx).trim();
      break;
    }
  }

  const paras = mainText.split(/\n{2,}/).filter((p) => p.trim());

  return (
    <>
      <div className={cn(compact ? "space-y-1.5" : "space-y-3")}>
        {paras.map((para, i) => {
          const lines = para.split("\n");
          return (
            <p
              key={i}
              className={cn(
                compact
                  ? "text-[11px] text-foreground/75 leading-relaxed"
                  : "text-[13px] text-foreground leading-[1.65]"
              )}
            >
              {lines.map((line, j) => (
                <span key={j}>
                  {renderWithLinks(line)}
                  {j < lines.length - 1 && <br />}
                </span>
              ))}
            </p>
          );
        })}
      </div>
      {sigText && <SignatureBlock text={sigText} />}
    </>
  );
}

// ── MessageCard ────────────────────────────────────────────────────────────────

function MessageCard({
  msg,
  index,
  total,
  internalDomains,
  defaultExpanded,
  senderNameOverride,
  senderEmailOverride,
}: {
  msg: ChainMessage;
  index: number;
  total: number;
  internalDomains: string[];
  defaultExpanded: boolean;
  senderNameOverride?: string;
  senderEmailOverride?: string;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  // Resolve sender — use overrides for the outermost message when no parsed sender
  const rawSender =
    msg.sender || (index === 0 && senderEmailOverride ? senderEmailOverride : "");
  const displayName =
    msg.sender
      ? senderDisplayName(msg.sender)
      : index === 0 && senderNameOverride
      ? senderNameOverride
      : "Unknown";
  const initials = rawSender ? senderInitials(rawSender) : displayName.slice(0, 2).toUpperCase() || "?";
  const outbound = isInternal(rawSender || displayName, internalDomains);

  const preview = msg.body.slice(0, 160);

  return (
    <div
      className={cn(
        "rounded-xl border text-xs transition-all duration-200",
        outbound
          ? "border-primary/25 bg-primary/5 border-l-[3px] border-l-primary/50"
          : "border-border/40 bg-muted/20 border-l-[3px] border-l-border/50",
        "hover:shadow-sm"
      )}
    >
      {/* Header */}
      <button
        className="w-full flex items-center gap-3 px-4 py-3 text-left"
        onClick={() => setExpanded((v) => !v)}
      >
        {/* Avatar */}
        <div
          className={cn(
            "h-7 w-7 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0",
            outbound ? "bg-primary/20 text-primary" : avatarColor(displayName)
          )}
        >
          {initials}
        </div>

        <div className="flex-1 min-w-0 space-y-0.5">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-foreground truncate">{displayName}</span>
            <Badge
              variant="outline"
              className={cn(
                "text-[9px] h-3.5 px-1 shrink-0",
                outbound
                  ? "text-primary border-primary/30 bg-primary/10"
                  : "text-muted-foreground border-border/40"
              )}
            >
              {outbound ? "Sent" : "Received"}
            </Badge>
          </div>
          {msg.date && (
            <p className="text-[11px] text-muted-foreground/60 truncate">
              {msg.date.length > 40 ? msg.date.slice(0, 40) + "…" : msg.date}
            </p>
          )}
        </div>

        {/* Message number */}
        <span className="text-[10px] text-muted-foreground/40 shrink-0">
          {index + 1}/{total}
        </span>

        {expanded ? (
          <ChevronDown className="h-3 w-3 text-muted-foreground/40 shrink-0" />
        ) : (
          <ChevronRight className="h-3 w-3 text-muted-foreground/40 shrink-0" />
        )}
      </button>

      {/* Collapsed preview */}
      {!expanded && (
        <p className="px-4 pb-3 text-[12px] text-muted-foreground line-clamp-2 leading-relaxed">
          {preview}
          {preview.length >= 160 ? "…" : ""}
        </p>
      )}

      {/* Expanded body */}
      {expanded && (
        <>
          <Separator className="opacity-30 mx-4" />
          <div className="px-4 py-3">{renderPlainBody(msg.body)}</div>
        </>
      )}
    </div>
  );
}

// ── Exported chain stats helper ────────────────────────────────────────────────

/**
 * Count sent/received messages in a raw email body by parsing the quoted chain.
 * Use this when you need accurate stats — Zoho only stores outbound emails, so
 * inbound replies only exist as quoted text inside body_full.
 *
 * @param rawBody    - email.body_full or email.body_preview
 * @param senderEmail - email.from of the outermost (newest) message
 * @param internalDomains - your team's email domains
 */
export function getChainStats(
  rawBody: string,
  senderEmail: string,
  internalDomains: string[],
): { sent: number; received: number } {
  const messages = parseEmailChain(rawBody);
  let sent = 0;
  let received = 0;
  messages.forEach((msg, i) => {
    // Outermost message has no parsed sender — use the raw email's from address
    const rawSender = msg.sender || (i === 0 ? senderEmail : "");
    if (!rawSender) return; // unknown sender, skip
    if (isInternal(rawSender, internalDomains)) sent++;
    else received++;
  });
  return { sent, received };
}

// ── EmailThreadView ────────────────────────────────────────────────────────────

export default function EmailThreadView({
  rawBody,
  subject,
  senderName,
  senderEmail,
  internalDomains = DEFAULT_INTERNAL_DOMAINS,
  className,
}: EmailThreadViewProps) {
  const messages = parseEmailChain(rawBody);
  const [expandAll, setExpandAll] = useState(false);

  if (messages.length === 0) {
    return (
      <p className="text-[11px] italic text-muted-foreground/40 px-1">
        No email content available.
      </p>
    );
  }

  // Default: only latest message (index 0) expanded
  const isExpanded = (i: number) => expandAll || i === 0;

  return (
    <div className={cn("space-y-3", className)}>
      {/* Thread header */}
      <div className="flex items-center justify-between px-1">
        <span className="text-[11px] text-muted-foreground/60">
          {messages.length} message{messages.length !== 1 ? "s" : ""} in thread
          {subject && (
            <span className="ml-1.5 text-foreground/70 font-medium truncate max-w-[260px] inline-block align-bottom">
              · {subject}
            </span>
          )}
        </span>
        {messages.length > 1 && (
          <button
            className="text-[10px] text-primary/70 hover:text-primary underline underline-offset-2 transition-colors"
            onClick={() => setExpandAll((v) => !v)}
          >
            {expandAll ? "Collapse all" : "Expand all"}
          </button>
        )}
      </div>

      {/* Message cards */}
      {messages.map((msg, i) => (
        <MessageCard
          key={i}
          msg={msg}
          index={i}
          total={messages.length}
          internalDomains={internalDomains}
          defaultExpanded={isExpanded(i)}
          senderNameOverride={senderName}
          senderEmailOverride={senderEmail}
        />
      ))}
    </div>
  );
}
