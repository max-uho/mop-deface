import { useEffect, useRef, useState } from "react";
import { invoke, convertFileSrc, isTauri } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import { open, save } from "@tauri-apps/plugin-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Upload, Shield, Download, LoaderCircle, Info } from "lucide-react";
import { basename } from "./workflow";
type Meta = {
  width: number;
  height: number;
  fps: string;
  duration: number;
  audio: boolean;
  codec: string;
};
type Event = {
  type: string;
  path?: string;
  metadata?: Meta;
  message?: string;
  frames?: number;
};
export default function App() {
  const [source, setSource] = useState(""),
    [output, setOutput] = useState(""),
    [meta, setMeta] = useState<Meta>(),
    [busy, setBusy] = useState(false),
    [status, setStatus] = useState(""),
    [error, setError] = useState(""),
    [compare, setCompare] = useState(false),
    [drag, setDrag] = useState(false),
    [license, setLicense] = useState(""),
    [exporting, setExporting] = useState(false);
  const video = useRef<HTMLVideoElement>(null),
    time = useRef(0),
    playing = useRef(false),
    busyRef = useRef(false),
    exportingRef = useRef(false),
    closing = useRef(false),
    loaded = useRef(false);
  function fail(e: unknown) {
    setError(String(e));
  }
  async function load(path: string) {
    if (busyRef.current || exportingRef.current) return;
    busyRef.current = true;
    loaded.current = false;
    setBusy(true);
    setError("");
    setStatus("Anonymizing video…");
    setOutput("");
    setMeta(undefined);
    setCompare(false);
    try {
      await invoke("start", {
        request: {
          action: "process",
          source: path,
          mode: "blur",
          threshold: 0.2,
          mosaic: 20,
          removeAudio: false,
        },
      });
      setSource(path);
      time.current = 0;
      playing.current = false;
    } catch (e) {
      busyRef.current = false;
      setBusy(false);
      fail(e);
    }
  }
  useEffect(() => {
    if (!isTauri()) {
      setError("Open the desktop application to select and process a video.");
      return;
    }
    let disposed = false;
    const cleanups: (() => void)[] = [];
    const register = async () => {
      const off = await listen<Event>("worker", ({ payload: e }) => {
        if (e.type === "closing") {
          closing.current = true;
          setStatus("Stopping before closing…");
        }
        if (e.type === "metadata" && e.metadata) setMeta(e.metadata);
        if (e.type === "progress") setStatus(e.message ?? "Processing…");
        if (e.type === "complete") {
          setError("");
          loaded.current = true;
          if (e.metadata) setMeta(e.metadata);
          if (e.path) {
            setOutput(e.path);
            setCompare(false);
            setStatus("Ready for review");
          } else setStatus("Ready");
        }
        if (e.type === "error") {
          setError(e.message ?? "Processing failed");
          setStatus("");
        }
        if (e.type === "cancelled") setStatus("Cancelled");
        if (e.type === "idle") {
          busyRef.current = false;
          setBusy(false);
          if (!loaded.current) setOutput("");
          if (closing.current) getCurrentWebview().window.close();
        }
      });
      if (disposed) off();
      else cleanups.push(off);
      const drop = await getCurrentWebview().onDragDropEvent(({ payload }) => {
        setDrag(payload.type === "over");
        if (payload.type === "drop" && payload.paths[0]) load(payload.paths[0]);
      });
      if (disposed) drop();
      else cleanups.push(drop);
    };
    register().catch(fail);
    return () => {
      disposed = true;
      cleanups.forEach((f) => f());
    };
  }, []);
  async function choose() {
    try {
      const path = await open({
        multiple: false,
        directory: false,
        filters: [
          {
            name: "Video",
            extensions: [
              "mp4",
              "mov",
              "mkv",
              "avi",
              "webm",
              "m4v",
              "mpeg",
              "mpg",
            ],
          },
        ],
      });
      if (typeof path === "string") await load(path);
    } catch (e) {
      fail(e);
    }
  }
  async function exportVideo() {
    exportingRef.current = true;
    setExporting(true);
    setError("");
    try {
      const destination = await save({
        defaultPath:
          basename(source).replace(/\.[^.]+$/, "") + "_anonymized.mp4",
        filters: [{ name: "MP4 video", extensions: ["mp4"] }],
      });
      if (destination) {
        const savedPath = await invoke<string>("export", { destination });
        time.current = video.current?.currentTime ?? 0;
        playing.current = !(video.current?.paused ?? true);
        setOutput(savedPath);
        setStatus("Saved successfully");
      }
    } catch (e) {
      fail(e);
    } finally {
      exportingRef.current = false;
      setExporting(false);
    }
  }
  function toggleCompare(next: boolean) {
    time.current = video.current?.currentTime ?? 0;
    playing.current = !(video.current?.paused ?? true);
    setCompare(next);
  }
  return (
    <TooltipProvider>
      <main className="mx-auto flex h-dvh max-w-6xl flex-col p-5 sm:p-7">
        <header className="mb-5 flex shrink-0 items-center justify-between">
          <div className="flex items-center gap-2">
            <Shield size={18} />
            <h1 className="text-base font-semibold">Deface</h1>
            <span className="ml-2 text-xs text-muted-foreground">
              Offline video anonymization
            </span>
          </div>
          <Dialog>
            <Tooltip>
              <TooltipTrigger asChild>
                <DialogTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label="About and licenses"
                    onClick={() =>
                      invoke<string>("licenses").then(setLicense).catch(fail)
                    }
                  >
                    <Info size={17} />
                  </Button>
                </DialogTrigger>
              </TooltipTrigger>
              <TooltipContent>About & licenses</TooltipContent>
            </Tooltip>
            <DialogContent className="max-w-2xl">
              <DialogHeader>
                <DialogTitle>Deface · 0.1.0</DialogTitle>
                <DialogDescription>
                  Local processing with deface 1.5.0 and CenterFace. No
                  accounts, telemetry, or cloud processing.
                </DialogDescription>
              </DialogHeader>
              <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap text-xs text-muted-foreground">
                {license ||
                  "License notices are generated during the sidecar build."}
              </pre>
            </DialogContent>
          </Dialog>
        </header>
        <div className="grid min-h-0 flex-1 grid-cols-1 gap-4">
          <Card className="min-h-0 overflow-hidden py-0 shadow-none">
            <CardContent className="flex min-h-0 flex-1 flex-col p-0">
              {source ? (
                <>
                  <div className="flex min-h-12 shrink-0 items-center justify-between gap-2 border-b px-4">
                    <span className="truncate font-medium" title={source}>
                      {basename(source)}
                    </span>
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={busy || exporting}
                      onClick={choose}
                    >
                      Change
                    </Button>
                  </div>
                  <div className="flex min-h-0 flex-1 items-center justify-center overflow-hidden">
                    <video
                      ref={video}
                      key={compare || !output ? source : output}
                      src={convertFileSrc(compare || !output ? source : output)}
                      controls
                      preload="metadata"
                      aria-label={
                        compare || !output
                          ? "Original video"
                          : "Anonymized video"
                      }
                      onLoadedMetadata={() => {
                        if (video.current) {
                          video.current.currentTime = Math.min(
                            time.current,
                            video.current.duration,
                          );
                          if (playing.current)
                            video.current.play().catch(() => {});
                        }
                      }}
                      onError={() =>
                        setError(
                          "This video cannot be previewed by the system webview. Processing may still work; the exported MP4 can be reviewed in a compatible player.",
                        )
                      }
                    />
                  </div>
                  <div className="flex min-h-12 shrink-0 items-center justify-between gap-2 border-t px-4">
                    <span className="text-xs text-muted-foreground">
                      {meta
                        ? `${meta.width} × ${meta.height} · ${Math.round(meta.duration)}s · ${meta.audio ? "Audio" : "No audio"}`
                        : busy
                          ? "Reading metadata…"
                          : ""}
                    </span>
                    {output && (
                      <div className="flex gap-1">
                        <Button
                          variant={compare ? "secondary" : "ghost"}
                          size="sm"
                          onClick={() => toggleCompare(true)}
                        >
                          Original
                        </Button>
                        <Button
                          variant={!compare ? "secondary" : "ghost"}
                          size="sm"
                          onClick={() => toggleCompare(false)}
                        >
                          Anonymized
                        </Button>
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <button
                  onClick={choose}
                  disabled={busy}
                  className={`flex min-h-0 w-full flex-1 flex-col items-center justify-center gap-3 p-8 outline-offset-[-4px] ${drag ? "bg-accent" : ""}`}
                >
                  <Upload size={28} className="text-muted-foreground" />
                  <span className="text-sm font-medium">Drop a video here</span>
                  <span className="text-xs text-muted-foreground">
                    or click to choose a file
                  </span>
                </button>
              )}
            </CardContent>
          </Card>
        </div>
        <div className="mt-4 flex shrink-0 justify-end gap-2">
          {busy && (
            <Button
              variant="secondary"
              onClick={() => {
                setStatus("Cancelling…");
                invoke("cancel").catch(fail);
              }}
            >
              Cancel
            </Button>
          )}
          <Button disabled={!output || busy || exporting} onClick={exportVideo}>
            <Download size={15} />
            {exporting ? "Saving…" : "Save MP4…"}
          </Button>
        </div>
        <div className="mt-4 shrink-0 space-y-3" aria-live="polite">
          {busy && (
            <Progress
              aria-label="Processing video"
              value={null}
              className="h-1 [&>div]:w-1/3 [&>div]:animate-pulse [&>div]:translate-x-0"
            />
          )}
          <p className="flex items-center gap-2 text-xs text-muted-foreground">
            {busy && <LoaderCircle size={13} className="animate-spin" />}
            {status || "Choose a video to get started."}
          </p>
          {error && (
            <p
              role="alert"
              className="break-words rounded-md border border-red-900 bg-red-950/30 px-3 py-2 text-xs text-red-300"
            >
              {error}
            </p>
          )}
          <p className="text-xs text-amber-200/80">
            Automatic detection can miss faces. Review the entire video before
            sharing.
          </p>
        </div>
      </main>
    </TooltipProvider>
  );
}
