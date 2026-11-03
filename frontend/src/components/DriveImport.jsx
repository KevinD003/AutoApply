"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import { Banner, Button, Card, ErrorText, Spinner } from "@/ui/primitives";
import { IconUpload } from "@/ui/icons";

/*
  Import a document from Google Drive (D124, Phase F) — owner-activated.

  Uses the Google Picker so you choose exactly one file; NoEfforts is granted the
  `drive.file` scope, which gives it access only to files you pick (never your whole
  Drive). The picked file is copied in as a new document version (a snapshot). It is
  never listed/scanned, never modified or deleted in Drive, and never sent to any AI
  provider. The section is hidden unless the owner has enabled and configured Drive
  on the server; the OAuth consent itself happens in the browser, when you click.
*/

const GAPI = "https://apis.google.com/js/api.js";
const GIS = "https://accounts.google.com/gsi/client";

function loadScript(src) {
  return new Promise((resolve, reject) => {
    if (document.querySelector(`script[src="${src}"]`)) return resolve();
    const s = document.createElement("script");
    s.src = src;
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("Could not load Google's scripts."));
    document.head.appendChild(s);
  });
}

export function DriveImport({ onImported }) {
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState("");
  const pickerReady = useRef(false);

  useEffect(() => {
    api("/integrations/drive/status")
      .then(setStatus)
      .catch(() => setStatus({ enabled: false }));
  }, []);

  const ensurePicker = useCallback(async () => {
    if (pickerReady.current) return;
    await loadScript(GAPI);
    await loadScript(GIS);
    await new Promise((resolve) => window.gapi.load("picker", { callback: resolve }));
    pickerReady.current = true;
  }, []);

  async function choose() {
    setError(null);
    setNotice("");
    setBusy(true);
    try {
      await ensurePicker();
      const token = await new Promise((resolve, reject) => {
        const client = window.google.accounts.oauth2.initTokenClient({
          client_id: status.client_id,
          scope: status.scope,
          callback: (r) => (r.access_token ? resolve(r.access_token) : reject(new Error("Access was not granted."))),
          error_callback: () => reject(new Error("Access was not granted.")),
        });
        client.requestAccessToken({ prompt: "" });
      });

      const view = new window.google.picker.DocsView(window.google.picker.ViewId.DOCS)
        .setMimeTypes(
          "application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,application/vnd.google-apps.document",
        )
        .setSelectFolderEnabled(false)
        .setOwnedByMe(true);

      const picker = new window.google.picker.PickerBuilder()
        .addView(view)
        .setOAuthToken(token)
        .setDeveloperKey(status.api_key)
        .setTitle("Choose a document to import")
        .setCallback(async (data) => {
          const A = window.google.picker.Action;
          if (data.action === A.CANCEL) {
            setBusy(false);
            return;
          }
          if (data.action !== A.PICKED) return;
          const f = data.docs[0];
          try {
            await api("/integrations/drive/import", {
              json: { file_id: f.id, access_token: token, name: f.name, mime_type: f.mimeType, kind: "resume" },
            });
            setNotice(`Imported “${f.name}”. It is a new version in your documents.`);
            onImported?.();
          } catch (e) {
            setError(e);
          } finally {
            setBusy(false);
          }
        })
        .build();
      picker.setVisible(true);
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  }

  // Off on this server → show nothing at all.
  if (!status || !status.enabled) return null;

  return (
    <Card title="Import from Google Drive">
      {!status.configured ? (
        <Banner tone="caution">
          Google Drive import is turned on but not fully configured on this server yet. It needs the owner&apos;s Google OAuth client id and
          API key.
        </Banner>
      ) : (
        <div className="space-y-3">
          <p className="text-sm text-ink-muted">
            Choose a PDF, DOCX or TXT (or a Google Doc, exported to PDF) from your Drive. NoEfforts only ever sees the one file you pick,
            copies it in as a new version, and never changes or deletes anything in your Drive.
          </p>
          <Button onClick={choose} disabled={busy}>
            {busy ? <Spinner /> : <IconUpload size={18} />}
            {busy ? "Working…" : "Import from Google Drive"}
          </Button>
          {notice && <Banner tone="positive">{notice}</Banner>}
          <ErrorText error={error} />
        </div>
      )}
    </Card>
  );
}
