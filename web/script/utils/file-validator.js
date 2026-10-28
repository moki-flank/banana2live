/**
 * banano2live - 文件验证工具模块 (借鉴并增强 W4J1e/Video2LivePhoto)
 * 同时兼容浏览器全局 window.Banano2Live 与 ES Module 导出
 */
(function (root) {
  class FileValidator {
    static isValidFileType(file, allowedTypes) {
      if (!file) {
        return { valid: false, message: '未选择文件' };
      }
      const ext = (file.name.split('.').pop() || '').toLowerCase();
      const mimeMatch = allowedTypes.some((type) =>
        (file.type && file.type.startsWith(type)) ||
        (type === 'image' && (file.type.startsWith('image/') || ['jpg', 'jpeg', 'png', 'webp', 'gif'].includes(ext))) ||
        (type === 'video' && (file.type.startsWith('video/') || ['mp4', 'mov', 'webm', 'mkv', 'm4v'].includes(ext)))
      );
      if (!mimeMatch) {
        return {
          valid: false,
          message: `不支持的文件类型 (${file.type || ext})，请上传 ${allowedTypes.join(' 或 ')} 文件`,
        };
      }
      return { valid: true };
    }

    static isFileSizeValid(file, maxSizeInMB = 200) {
      const sizeMB = file.size / (1024 * 1024);
      if (sizeMB > maxSizeInMB) {
        return {
          valid: false,
          message: `文件大小超出限制: ${sizeMB.toFixed(2)}MB > ${maxSizeInMB}MB`,
        };
      }
      return { valid: true };
    }

    static formatBytes(bytes) {
      if (!bytes || bytes <= 0) return '0 B';
      if (bytes < 1024) return bytes + ' B';
      if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
      return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
    }
  }

  root.Banano2Live = root.Banano2Live || {};
  root.Banano2Live.FileValidator = FileValidator;
})(typeof window !== 'undefined' ? window : globalThis);
