/**
 * 统一的文本复制工具:
 * navigator.clipboard 仅在安全上下文 (HTTPS / localhost) 可用,
 * 移动端通过局域网 http 访问时为 undefined → 回退到 textarea + execCommand。
 */
export const copyText = async (text: string): Promise<boolean> => {
  const content = String(text ?? '');
  if (!content) return false;

  try {
    if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(content);
      return true;
    }
  } catch {
    /* 继续走回退方案 */
  }

  try {
    const ta = document.createElement('textarea');
    ta.value = content;
    ta.setAttribute('readonly', '');
    ta.style.position = 'fixed';
    ta.style.top = '-9999px';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    ta.setSelectionRange(0, content.length);
    const ok = document.execCommand('copy');
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
};
