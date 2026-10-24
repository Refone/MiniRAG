import { useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { UploadIcon } from "@/components/icons/AppIcons";
import { UPLOAD_ACCEPT } from "@/lib/constants";

interface UploadDropzoneProps {
  onFiles: (list: FileList) => void;
}

/** 点击/拖拽上传区（dragging 视觉内部自持；原 ImportPage 上传区平移） */
export function UploadDropzone({ onFiles }: UploadDropzoneProps) {
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    onFiles(e.dataTransfer.files);
  };

  const onInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) onFiles(e.target.files);
    e.target.value = "";
  };

  return (
    <div
      className={`upload-area${dragging ? " dragging" : ""}`}
      onClick={() => fileInputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
    >
      <div className="upload-icon">
        <UploadIcon />
      </div>
      <p>点击或拖拽文件到此处 (PDF / MD / ZIP)</p>
      <p className="sub">
        ZIP 为 markdown 合集，包内每个 md 将成为一篇独立文档
      </p>
      <input
        ref={fileInputRef}
        type="file"
        className="file-input"
        multiple
        accept={UPLOAD_ACCEPT}
        onChange={onInputChange}
      />
    </div>
  );
}
