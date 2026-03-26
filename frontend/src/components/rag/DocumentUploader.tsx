/**
 * Document Uploader Component
 * 
 * Drag and drop file upload with progress indication
 */
import { useState, useCallback, useRef } from 'react';
import { Upload, X, FileText, Loader2, CheckCircle, AlertCircle } from 'lucide-react';
import { useRagStore } from '../../stores/ragStore';
import clsx from 'clsx';

const ACCEPTED_TYPES = [
  'application/pdf',
  'text/plain',
  'text/markdown',
  'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
];

const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB

export default function DocumentUploader() {
  const { uploadDocument, uploadProgress, currentCollectionId } = useRagStore();
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(
    async (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);

      const files = Array.from(e.dataTransfer.files);
      for (const file of files) {
        if (validateFile(file)) {
          await uploadDocument(file);
        }
      }
    },
    [uploadDocument]
  );

  const handleFileSelect = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(e.target.files || []);
      for (const file of files) {
        if (validateFile(file)) {
          await uploadDocument(file);
        }
      }
      // Reset input
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    },
    [uploadDocument]
  );

  const validateFile = (file: File): boolean => {
    if (!ACCEPTED_TYPES.includes(file.type) && !file.name.endsWith('.md')) {
      alert(`不支持的文件类型: ${file.name}`);
      return false;
    }
    if (file.size > MAX_FILE_SIZE) {
      alert(`文件过大: ${file.name} (最大 50MB)`);
      return false;
    }
    return true;
  };

  const progressArray = Array.from(uploadProgress.entries());

  return (
    <div className="space-y-4">
      {/* Drop Zone */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={clsx(
          'relative border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition',
          isDragging
            ? 'border-primary-500 bg-primary-500/10'
            : 'border-slate-600 hover:border-slate-500 hover:bg-slate-800/50',
          !currentCollectionId && 'opacity-50 pointer-events-none'
        )}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.txt,.md,.doc,.docx"
          onChange={handleFileSelect}
          className="hidden"
          disabled={!currentCollectionId}
        />

        <div className="flex flex-col items-center gap-3">
          <div
            className={clsx(
              'w-12 h-12 rounded-full flex items-center justify-center transition',
              isDragging ? 'bg-primary-500/20' : 'bg-slate-700'
            )}
          >
            <Upload
              className={clsx(
                'w-6 h-6 transition',
                isDragging ? 'text-primary-400' : 'text-slate-400'
              )}
            />
          </div>

          <div>
            <p className="text-sm font-medium text-white">
              {isDragging ? '释放以上传文件' : '拖拽文件到此处上传'}
            </p>
            <p className="text-xs text-slate-500 mt-1">
              或点击选择文件 · 支持 PDF, TXT, MD, DOC, DOCX · 最大 50MB
            </p>
          </div>
        </div>

        {!currentCollectionId && (
          <div className="absolute inset-0 flex items-center justify-center bg-slate-900/80 rounded-xl">
            <p className="text-sm text-slate-400">请先选择或创建一个集合</p>
          </div>
        )}
      </div>

      {/* Upload Progress List */}
      {progressArray.length > 0 && (
        <div className="space-y-2">
          {progressArray.map(([key, progress]) => (
            <div
              key={key}
              className="flex items-center gap-3 p-3 bg-slate-800/50 rounded-lg border border-slate-700"
            >
              <div className="w-8 h-8 bg-slate-700 rounded-lg flex items-center justify-center">
                <FileText className="w-4 h-4 text-slate-400" />
              </div>

              <div className="flex-1 min-w-0">
                <p className="text-sm text-white truncate">{progress.filename}</p>
                <div className="flex items-center gap-2 mt-1">
                  {/* Progress Bar */}
                  <div className="flex-1 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                    <div
                      className={clsx(
                        'h-full transition-all duration-300',
                        progress.status === 'completed' && 'bg-green-500',
                        progress.status === 'failed' && 'bg-red-500',
                        (progress.status === 'uploading' || progress.status === 'processing') &&
                          'bg-primary-500'
                      )}
                      style={{ width: `${progress.progress}%` }}
                    />
                  </div>
                  <span className="text-xs text-slate-500 w-12 text-right">
                    {progress.progress}%
                  </span>
                </div>
              </div>

              {/* Status Icon */}
              <div className="flex-shrink-0">
                {progress.status === 'uploading' && (
                  <Loader2 className="w-5 h-5 text-primary-400 animate-spin" />
                )}
                {progress.status === 'processing' && (
                  <Loader2 className="w-5 h-5 text-yellow-400 animate-spin" />
                )}
                {progress.status === 'completed' && (
                  <CheckCircle className="w-5 h-5 text-green-400" />
                )}
                {progress.status === 'failed' && (
                  <AlertCircle className="w-5 h-5 text-red-400" />
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
