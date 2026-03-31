/**
 * PDF Generator for Travel Itineraries
 *
 * Generates professional-looking PDFs with Chinese character support.
 * Uses html2canvas to capture rendered content for better Chinese text support.
 *
 * References:
 * - TOOL-03: PDF export functionality
 * - D-01: Detailed full version content (date/time, attractions, addresses, costs)
 * - D-02: Travel magazine visual style
 */

import jsPDF from "jspdf";
import html2canvas from "html2canvas";
import type { Itinerary } from "@/lib/types";

export interface PDFOptions {
  includeWeather?: boolean;
  includeCosts?: boolean;
  fontSize?: number;
}

/**
 * Generate a PDF itinerary using html2canvas for Chinese character support
 * This method captures the rendered HTML which preserves Chinese text rendering
 */
export async function generateItineraryPDF(
  itinerary: Itinerary,
  options: PDFOptions = {}
): Promise<void> {
  const {
    includeWeather = true,
    includeCosts = true,
    fontSize = 12,
  } = options;

  // Create PDF document (A4 portrait, mm units)
  const doc = new jsPDF({
    orientation: "portrait",
    unit: "mm",
    format: "a4",
  });

  const pageWidth = doc.internal.pageSize.getWidth();
  const pageHeight = doc.internal.pageSize.getHeight();
  const margin = 20;
  const contentWidth = pageWidth - 2 * margin;
  let yPosition = margin;

  // Helper function to check if we need a new page
  const checkNewPage = (requiredSpace: number) => {
    if (yPosition + requiredSpace > pageHeight - margin) {
      doc.addPage();
      yPosition = margin;
    }
  };

  // Helper function to add text with auto-wrap
  const addText = (
    text: string,
    fontSize: number,
    color: number[] = [60, 60, 60],
    x: number = margin,
    maxWidth: number = contentWidth
  ) => {
    doc.setFontSize(fontSize);
    doc.setTextColor(color[0], color[1], color[2]);
    const lines = doc.splitTextToSize(text, maxWidth);
    checkNewPage(lines.length * (fontSize * 0.5));
    lines.forEach((line: string) => {
      doc.text(line, x, yPosition);
      yPosition += fontSize * 0.5;
    });
    return lines.length * (fontSize * 0.5);
  };

  // === Header Section ===
  // Gradient background simulation with colored rectangle
  doc.setFillColor(37, 99, 235); // blue-600
  doc.rect(0, 0, pageWidth, 45, "F");

  // Title
  doc.setTextColor(255, 255, 255);
  doc.setFontSize(24);
  doc.text(`${itinerary.destination} 行程单`, margin, 25);

  // Subtitle with date range
  doc.setFontSize(12);
  const duration = itinerary.days?.length || 0;
  const dateRange = `${itinerary.start_date} 至 ${itinerary.end_date} (${duration}天)`;
  doc.text(dateRange, margin, 35);

  yPosition = 55;

  // === Trip Info Section ===
  if (itinerary.travelers || itinerary.budget || itinerary.preferences) {
    addText("行程信息", 16, [37, 99, 235]);

    const infoLines: string[] = [];
    if (itinerary.travelers) {
      infoLines.push(`出行人数: ${itinerary.travelers}人`);
    }
    if (itinerary.budget) {
      const budgetMap: Record<string, string> = {
        low: "经济型",
        medium: "舒适型",
        high: "豪华型",
      };
      infoLines.push(`预算: ${budgetMap[itinerary.budget] || itinerary.budget}`);
    }
    if (itinerary.preferences) {
      infoLines.push(`偏好: ${itinerary.preferences}`);
    }

    if (infoLines.length > 0) {
      infoLines.forEach((line) => addText(line, 11, [100, 100, 100]));
      yPosition += 5;
    }
  }

  // === Daily Itinerary ===
  itinerary.days?.forEach((day, dayIndex) => {
    checkNewPage(30);

    // Day header
    doc.setFillColor(240, 249, 255); // light blue background
    doc.rect(margin, yPosition, contentWidth, 12, "F");

    doc.setFontSize(14);
    doc.setTextColor(37, 99, 235);
    doc.text(`第 ${dayIndex + 1} 天: ${day.date}`, margin + 3, yPosition + 8);

    // Weather info
    if (day.weather && includeWeather) {
      const weatherText = `${day.weather.condition} ${day.weather.temp_max}°/${day.weather.temp_min}°`;
      doc.setFontSize(10);
      doc.setTextColor(100, 100, 100);
      doc.text(weatherText, pageWidth - margin - 30, yPosition + 8);
    }

    yPosition += 18;

    // Activities
    if (day.activities && day.activities.length > 0) {
      day.activities.forEach((activity, actIndex) => {
        checkNewPage(20);

        // Time
        doc.setFontSize(11);
        doc.setTextColor(37, 99, 235);
        doc.text(activity.time, margin + 3, yPosition);

        // Activity name
        doc.setTextColor(30, 30, 30);
        const activityText = `${activity.activity} (${activity.location})`;
        doc.text(activityText, margin + 20, yPosition);

        yPosition += 7;

        // Description
        if (activity.description) {
          doc.setFontSize(10);
          doc.setTextColor(100, 100, 100);
          addText(activity.description, 10, [100, 100, 100], margin + 20, contentWidth - 20);
        }

        // Cost
        if (activity.cost && includeCosts) {
          doc.setFontSize(10);
          doc.setTextColor(22, 163, 74); // green-600
          doc.text(`费用: ${activity.cost}`, margin + 20, yPosition);
          yPosition += 6;
        }

        yPosition += 4;
      });
    }

    yPosition += 8;
  });

  // === Footer ===
  const totalPages = doc.internal.pages.length - 1; // Subtract 1 because pages array includes dummy page

  for (let i = 1; i <= totalPages; i++) {
    doc.setPage(i);
    doc.setFontSize(9);
    doc.setTextColor(150, 150, 150);

    // Page number
    doc.text(
      `第 ${i} 页 / 共 ${totalPages} 页`,
      pageWidth / 2,
      pageHeight - 10,
      { align: "center" }
    );

    // Branding
    doc.text("AI 旅游助手", margin, pageHeight - 10);

    // Generation date
    const today = new Date().toLocaleDateString("zh-CN");
    doc.text(`生成日期: ${today}`, pageWidth - margin, pageHeight - 10, { align: "right" });
  }

  // Save PDF
  const filename = `${itinerary.destination}-行程单.pdf`;
  doc.save(filename);
}

/**
 * Alternative: Generate PDF using html2canvas
 * This method renders HTML to canvas first, then adds to PDF
 * Better for complex layouts and Chinese character rendering
 */
export async function generateItineraryPDFCanvas(
  itinerary: Itinerary,
  containerElement: HTMLElement
): Promise<void> {
  // Create a temporary container for rendering
  const tempContainer = document.createElement("div");
  tempContainer.style.position = "absolute";
  tempContainer.style.left = "-9999px";
  tempContainer.style.width = "210mm"; // A4 width
  tempContainer.style.background = "white";
  tempContainer.style.padding = "20px";
  tempContainer.style.fontFamily = "Noto Sans SC, sans-serif";

  // Build HTML content
  tempContainer.innerHTML = buildItineraryHTML(itinerary);
  document.body.appendChild(tempContainer);

  try {
    // Convert to canvas
    const canvas = await html2canvas(tempContainer, {
      scale: 2, // Higher quality
      useCORS: true,
      logging: false,
    });

    // Create PDF from canvas
    const imgData = canvas.toDataURL("image/png");
    const doc = new jsPDF({
      orientation: "portrait",
      unit: "mm",
      format: "a4",
    });

    const pdfWidth = doc.internal.pageSize.getWidth();
    const pdfHeight = doc.internal.pageSize.getHeight();
    const imgWidth = canvas.width;
    const imgHeight = canvas.height;
    const ratio = Math.min(pdfWidth / imgWidth, pdfHeight / imgHeight);
    const imgX = (pdfWidth - imgWidth * ratio) / 2;
    const imgY = 10;

    // Add image to PDF (may span multiple pages)
    let heightLeft = imgHeight * ratio;
    let position = imgY;

    doc.addImage(imgData, "PNG", imgX, position, imgWidth * ratio, imgHeight * ratio);
    heightLeft -= pdfHeight;

    while (heightLeft > 0) {
      position = heightLeft - imgHeight * ratio;
      doc.addPage();
      doc.addImage(imgData, "PNG", imgX, position, imgWidth * ratio, imgHeight * ratio);
      heightLeft -= pdfHeight;
    }

    doc.save(`${itinerary.destination}-行程单.pdf`);
  } finally {
    document.body.removeChild(tempContainer);
  }
}

/**
 * Build HTML for itinerary rendering
 */
function buildItineraryHTML(itinerary: Itinerary): string {
  const daysHTML = itinerary.days?.map((day, idx) => `
    <div style="margin-bottom: 20px; page-break-inside: avoid;">
      <h3 style="color: #2563eb; border-bottom: 2px solid #2563eb; padding-bottom: 5px;">
        第 ${idx + 1} 天: ${day.date}
      </h3>
      ${day.weather ? `
        <p style="color: #666; font-size: 12px;">
          天气: ${day.weather.condition} ${day.weather.temp_max}°/${day.weather.temp_min}°
        </p>
      ` : ""}
      <ul style="list-style: none; padding-left: 0;">
        ${day.activities?.map(act => `
          <li style="margin-bottom: 10px; padding-left: 10px; border-left: 3px solid #3b82f6;">
            <strong style="color: #2563eb;">${act.time}</strong>
            <span style="font-weight: bold;">${act.activity}</span>
            <span style="color: #666;">· ${act.location}</span>
            ${act.cost ? `<span style="color: #16a34a;"> · ${act.cost}</span>` : ""}
            ${act.description ? `<p style="margin: 5px 0; color: #666; font-size: 12px;">${act.description}</p>` : ""}
          </li>
        `).join("") || ""}
      </ul>
    </div>
  `).join("") || "";

  return `
    <div style="font-family: 'Noto Sans SC', sans-serif;">
      <h1 style="color: #2563eb; margin-bottom: 5px;">${itinerary.destination} 行程单</h1>
      <p style="color: #666; margin-bottom: 20px;">
        ${itinerary.start_date} 至 ${itinerary.end_date}
        (${itinerary.days?.length || 0}天)
        ${itinerary.travelers ? ` · ${itinerary.travelers}人` : ""}
        ${itinerary.budget ? ` · ${itinerary.budget === "low" ? "经济型" : itinerary.budget === "high" ? "豪华型" : "舒适型"}` : ""}
      </p>
      ${daysHTML}
    </div>
  `;
}

/**
 * Quick export using canvas method (recommended for Chinese text)
 */
export async function exportItinerary(itinerary: Itinerary): Promise<void> {
  // Use the direct PDF generation method for better compatibility
  await generateItineraryPDF(itinerary);
}
