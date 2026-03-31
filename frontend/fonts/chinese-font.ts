/**
 * Chinese Font Support for jsPDF
 *
 * This file provides Chinese font support for PDF generation.
 * For production use, convert a TTF font to base64 using:
 * https://parallax.github.io/jsPDF/generate-font/
 *
 * Current implementation uses a minimal subset approach.
 * For full Chinese support, replace CHINESE_FONT_BASE64 with
 * the base64 output from the font converter.
 */

// Base64 encoded Noto Sans SC font (subset for common Chinese characters)
// This is a placeholder - for production, use the full font from the converter
export const CHINESE_FONT_BASE64 = "";

// Font name for jsPDF
export const CHINESE_FONT_NAME = "NotoSansSC";

// Font file name for VFS
export const CHINESE_FONT_FILENAME = "NotoSansSC.ttf";

/**
 * Alternative: Use browser's font loading API to get system fonts
 * This is a fallback method that doesn't require base64 encoding
 */
export async function loadChineseFontFromSystem(): Promise<ArrayBuffer | null> {
  try {
    // Try to load a Chinese font from the system
    const fontFace = new FontFace(
      "ChineseFont",
      "url(https://fonts.gstatic.com/s/notosanssc/v36/k3kJo84MPvpLmixcA63oeALhLOCT-xWNm8Hqd37x1-A.woff2)"
    );
    await fontFace.load();
    document.fonts.add(fontFace);
    return null; // Signal that we're using browser fonts
  } catch (error) {
    console.warn("Failed to load Chinese font from system:", error);
    return null;
  }
}

/**
 * For true Chinese PDF support, use one of these methods:
 *
 * 1. Base64 Font (Recommended for offline support):
 *    - Download Noto Sans SC from Google Fonts
 *    - Convert to base64 using https://parallax.github.io/jsPDF/generate-font/
 *    - Replace CHINESE_FONT_BASE64 with the output
 *
 * 2. CDN Font Loading:
 *    - Load font from CDN in the browser
 *    - Use html2canvas to capture rendered HTML
 *    - This preserves Chinese text rendering
 *
 * 3. Simplified Chinese (for demo/testing):
 *    - Use English labels for testing
 *    - Replace with full Chinese font in production
 */

export const CHINESE_FONT_CONFIG = {
  name: CHINESE_FONT_NAME,
  filename: CHINESE_FONT_FILENAME,
  hasBase64: CHINESE_FONT_BASE64.length > 0,
};
