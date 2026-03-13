import { useRef, useEffect } from 'react';

interface HtmlSandboxProps {
  html: string;
  className?: string;
}

/**
 * Safely renders rich HTML content within a sandboxed iframe.
 * Uses srcdoc to isolate styles and prevent script execution.
 */
export function HtmlSandbox({ html, className = "" }: HtmlSandboxProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe) return;

    // Function to adjust height based on content
    const updateHeight = () => {
      if (iframe.contentWindow && iframe.contentDocument) {
        const body = iframe.contentDocument.body;
        const htmlElement = iframe.contentDocument.documentElement;
        const height = Math.max(
          body.scrollHeight,
          body.offsetHeight,
          htmlElement.clientHeight,
          htmlElement.scrollHeight,
          htmlElement.offsetHeight
        );
        iframe.style.height = `${height}px`;
      }
    };

    // Initial height update
    updateHeight();

    // Secondary update after images/styles load
    iframe.onload = updateHeight;

    // Observer for dynamic content changes
    const observer = new MutationObserver(updateHeight);
    if (iframe.contentDocument) {
      observer.observe(iframe.contentDocument.body, {
        childList: true,
        subtree: true,
        attributes: true
      });
    }

    return () => observer.disconnect();
  }, [html]);

  // Modern Outlook/HTML email normalization styles
  const normalizedHtml = `
    <!DOCTYPE html>
    <html>
      <head>
        <style>
          body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            font-size: 14px;
            line-height: 1.6;
            color: #334155;
            margin: 0;
            padding: 4px;
            word-wrap: break-word;
            white-space: pre-wrap; /* Ensure plain text line breaks are respected */
          }
          img {
            max-width: 100%;
            height: auto;
            display: block;
          }
          a {
            color: #4f46e5;
            text-decoration: underline;
          }
          blockquote {
            border-left: 2px solid #e2e8f0;
            margin: 1em 0;
            padding-left: 1em;
            color: #64748b;
          }
          table {
            border-collapse: collapse;
            width: 100% !important;
          }
        </style>
      </head>
      <body>
        ${html}
      </body>
    </html>
  `;

  return (
    <iframe
      ref={iframeRef}
      title="Email Content"
      srcDoc={normalizedHtml}
      className={`w-full border-none overflow-hidden ${className}`}
      sandbox="allow-popups allow-popups-to-escape-sandbox"
      loading="lazy"
    />
  );
}
