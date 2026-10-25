import { useEffect, useRef, type MutableRefObject } from "react";

export function MarkdownPreview({
  html,
  scrollRef,
  emptyText,
}: {
  html: string;
  scrollRef: MutableRefObject<HTMLDivElement | null>;
  emptyText: string;
}) {
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const root = contentRef.current;
    if (!root) return;
    const buttons: HTMLButtonElement[] = [];
    const blocks = root.querySelectorAll<HTMLElement>(".codeblock");
    blocks.forEach((block) => {
      if (block.querySelector(".code-copy")) return;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "code-copy";
      button.textContent = "Copy";
      button.setAttribute("aria-label", "Copy code block");
      let timer = 0;
      const copy = () => {
        const text = block.querySelector("code")?.textContent ?? "";
        void navigator.clipboard
          ?.writeText(text)
          .then(() => {
            button.textContent = "Copied";
            button.dataset.state = "copied";
            window.clearTimeout(timer);
            timer = window.setTimeout(() => {
              button.textContent = "Copy";
              delete button.dataset.state;
            }, 1600);
          })
          .catch(() => {
            button.textContent = "Failed";
            window.clearTimeout(timer);
            timer = window.setTimeout(() => {
              button.textContent = "Copy";
            }, 1600);
          });
      };
      button.addEventListener("click", copy);
      block.appendChild(button);
      buttons.push(button);
    });
    return () => {
      buttons.forEach((button) => button.remove());
    };
  }, [html]);

  return (
    <div ref={scrollRef} className="preview-scroll">
      <div className="preview-inner">
        <div ref={contentRef}>
          {html ? (
            <div
              className="markdown"
              dangerouslySetInnerHTML={{ __html: html }}
            />
          ) : (
            <div className="markdown">
              <p className="preview-empty">{emptyText}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
