"use client";

import { useEffect } from "react";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Image from "@tiptap/extension-image";
import { Table } from "@tiptap/extension-table";
import { TableRow } from "@tiptap/extension-table-row";
import { TableHeader } from "@tiptap/extension-table-header";
import { TableCell } from "@tiptap/extension-table-cell";
import { comprimirImagem, isImageFile } from "@/lib/image-compress";
import { cn } from "@/lib/utils";
import {
  BoldIcon,
  ItalicIcon,
  ListIcon,
  ListOrderedIcon,
  Heading2Icon,
  Heading3Icon,
  PilcrowIcon,
  TableIcon,
  Undo2Icon,
  Redo2Icon,
  RemoveFormattingIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";

interface EditorParecerProps {
  content: string;
  editable?: boolean;
  onChange?: (html: string) => void;
  placeholder?: string;
  className?: string;
}

async function inserirImagensDoEvento(
  event: ClipboardEvent | DragEvent,
  editor: ReturnType<typeof useEditor> | null,
  onChange?: (html: string) => void
) {
  if (!editor) return;

  let files: File[] = [];

  if (event instanceof ClipboardEvent) {
    const clipboardData = event.clipboardData;
    if (!clipboardData) return;
    const items = Array.from(clipboardData.items);
    const imageFiles = items
      .filter((item) => item.type.startsWith("image/"))
      .map((item) => item.getAsFile())
      .filter((f): f is File => f !== null);
    if (imageFiles.length === 0) return;
    event.preventDefault();
    files = imageFiles;
  } else {
    event.preventDefault();
    const dataTransfer = event.dataTransfer;
    if (!dataTransfer) return;
    files = Array.from(dataTransfer.files).filter(isImageFile);
  }

  for (const file of files) {
    try {
      const dataUri = await comprimirImagem(file);
      if (dataUri) {
        editor.chain().focus().setImage({ src: dataUri }).run();
      }
    } catch {
      // skip failed images
    }
  }
  if (onChange) {
    onChange(editor.getHTML());
  }
}

function Toolbar({ editor }: { editor: ReturnType<typeof useEditor> | null }) {
  if (!editor) return null;

  const btnClass = "p-1.5";
  const btnData = "size-4";

  return (
    <div className="flex flex-wrap items-center gap-0.5 border-b border-border px-2 py-1">
      <Button
        variant="ghost"
        size="icon-xs"
        className={btnClass}
        aria-label="Desfazer"
        disabled={!editor.can().undo()}
        onClick={() => editor.chain().focus().undo().run()}
      >
        <Undo2Icon className={btnData} />
      </Button>
      <Button
        variant="ghost"
        size="icon-xs"
        className={btnClass}
        aria-label="Refazer"
        disabled={!editor.can().redo()}
        onClick={() => editor.chain().focus().redo().run()}
      >
        <Redo2Icon className={btnData} />
      </Button>

      <div className="mx-1 h-5 w-px bg-border" />

      <Button
        variant="ghost"
        size="icon-xs"
        className={btnClass}
        aria-label="Paragrafo"
        onClick={() => editor.chain().focus().setParagraph().run()}
        data-active={editor.isActive("paragraph") ? "" : undefined}
      >
        <PilcrowIcon className={btnData} />
      </Button>
      <Button
        variant="ghost"
        size="icon-xs"
        className={btnClass}
        aria-label="Ttulo 2"
        onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
        data-active={editor.isActive("heading", { level: 2 }) ? "" : undefined}
      >
        <Heading2Icon className={btnData} />
      </Button>
      <Button
        variant="ghost"
        size="icon-xs"
        className={btnClass}
        aria-label="Ttulo 3"
        onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
        data-active={editor.isActive("heading", { level: 3 }) ? "" : undefined}
      >
        <Heading3Icon className={btnData} />
      </Button>

      <div className="mx-1 h-5 w-px bg-border" />

      <Button
        variant="ghost"
        size="icon-xs"
        className={btnClass}
        aria-label="Negrito"
        onClick={() => editor.chain().focus().toggleBold().run()}
        data-active={editor.isActive("bold") ? "" : undefined}
      >
        <BoldIcon className={btnData} />
      </Button>
      <Button
        variant="ghost"
        size="icon-xs"
        className={btnClass}
        aria-label="Italico"
        onClick={() => editor.chain().focus().toggleItalic().run()}
        data-active={editor.isActive("italic") ? "" : undefined}
      >
        <ItalicIcon className={btnData} />
      </Button>
      <Button
        variant="ghost"
        size="icon-xs"
        className={btnClass}
        aria-label="Limpar formatacao"
        onClick={() => editor.chain().focus().unsetAllMarks().clearNodes().run()}
      >
        <RemoveFormattingIcon className={btnData} />
      </Button>

      <div className="mx-1 h-5 w-px bg-border" />

      <Button
        variant="ghost"
        size="icon-xs"
        className={btnClass}
        aria-label="Lista"
        onClick={() => editor.chain().focus().toggleBulletList().run()}
        data-active={editor.isActive("bulletList") ? "" : undefined}
      >
        <ListIcon className={btnData} />
      </Button>
      <Button
        variant="ghost"
        size="icon-xs"
        className={btnClass}
        aria-label="Lista numerada"
        onClick={() => editor.chain().focus().toggleOrderedList().run()}
        data-active={editor.isActive("orderedList") ? "" : undefined}
      >
        <ListOrderedIcon className={btnData} />
      </Button>

      <div className="mx-1 h-5 w-px bg-border" />

      <Button
        variant="ghost"
        size="icon-xs"
        className={btnClass}
        aria-label="Inserir tabela"
        onClick={() =>
          editor
            .chain()
            .focus()
            .insertTable({ rows: 3, cols: 3, withHeaderRow: true })
            .run()
        }
      >
        <TableIcon className={btnData} />
      </Button>
    </div>
  );
}

export function EditorParecer({
  content,
  editable = true,
  onChange,
  placeholder,
  className,
}: EditorParecerProps) {
  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [1, 2, 3] },
        codeBlock: false,
        blockquote: false,
        horizontalRule: {},
      }),
      Image.configure({ inline: false, allowBase64: true }),
      Table.configure({ resizable: false }),
      TableRow,
      TableHeader,
      TableCell,
    ],
    content,
    editable,
    immediatelyRender: false,
    editorProps: {
      attributes: {
        class: cn(
          "prose prose-sm max-w-none min-h-[420px] p-4 focus:outline-none",
          "[&_table]:w-full [&_table]:border-collapse [&_table]:border [&_table]:border-border",
          "[&_th]:border [&_th]:border-border [&_th]:bg-muted [&_th]:px-2 [&_th]:py-1 [&_th]:text-left [&_th]:text-xs [&_th]:font-medium",
          "[&_td]:border [&_td]:border-border [&_td]:px-2 [&_td]:py-1 [&_td]:text-xs",
          "[&_img]:max-w-full [&_img]:rounded-md [&_img]:my-2",
          "[&_hr]:my-4 [&_hr]:border-border"
        ),
      },
      handlePaste: (_view, event) => {
        inserirImagensDoEvento(event, editor, onChange);
        return false;
      },
      handleDrop: (_view, event, _moved, _direct) => {
        const hasFiles =
          event.dataTransfer?.files && event.dataTransfer.files.length > 0;
        if (hasFiles) {
          inserirImagensDoEvento(event, editor, onChange);
          return true;
        }
        return false;
      },
    },
    onUpdate: ({ editor }) => {
      onChange?.(editor.getHTML());
    },
  });

  useEffect(() => {
    if (editor && !editor.isDestroyed) {
      const currentContent = editor.getHTML();
      if (currentContent !== content) {
        editor.commands.setContent(content);
      }
    }
  }, [content, editor]);

  if (!editor) return null;

  return (
    <div className={cn("rounded-lg border border-border overflow-hidden", className)}>
      {editable && <Toolbar editor={editor} />}
      <EditorContent editor={editor} role="textbox" aria-label={placeholder} />
      {editable && editor.isEmpty && placeholder && (
        <div className="pointer-events-none absolute top-14 left-4 text-muted-foreground text-sm select-none">
          {placeholder}
        </div>
      )}
    </div>
  );
}
