/**
 * Investment Memo Word Export
 *
 * Creates professional Word documents matching InvestmentMemoView UI formatting
 */

import {
  Document,
  Packer,
  Paragraph,
  TextRun,
  HeadingLevel,
  AlignmentType,
  BorderStyle,
} from "docx";

/**
 * Export Investment Memo as professional Word document
 * @param {Object} artifact - Investment memo artifact data
 * @param {Object} run - Workflow run metadata
 */
export async function exportInvestmentMemoAsWord(artifact, run) {
  if (!artifact) {
    throw new Error("No investment memo data to export");
  }

  const data = artifact.parsed || artifact;
  const companyName = data.company_overview?.company_name || "Investment Memo";
  const currency = data.currency || run?.currency || "USD";
  const dateStr = new Date(run?.created_at || Date.now()).toLocaleDateString();

  const children = [];

  // ========== COVER PAGE ==========
  children.push(
    new Paragraph({
      text: companyName,
      heading: HeadingLevel.TITLE,
      alignment: AlignmentType.CENTER,
      spacing: { after: 200 },
    }),

    new Paragraph({
      text: "Investment Memo",
      heading: HeadingLevel.HEADING_1,
      alignment: AlignmentType.CENTER,
      spacing: { after: 300 },
    })
  );

  // Industry
  if (data.company_overview?.industry) {
    children.push(
      new Paragraph({
        text: data.company_overview.industry,
        alignment: AlignmentType.CENTER,
        spacing: { after: 200 },
      })
    );
  }

  // Metadata
  children.push(
    new Paragraph({
      children: [
        new TextRun({
          text: `Generated: ${dateStr}`,
          bold: true,
        }),
      ],
      alignment: AlignmentType.CENTER,
      spacing: { after: 100 },
    })
  );

  if (run?.latency_ms) {
    children.push(
      new Paragraph({
        text: `Processing Time: ${(run.latency_ms / 1000).toFixed(1)}s`,
        alignment: AlignmentType.CENTER,
        spacing: { after: 50 },
      })
    );
  }

  // Divider
  children.push(
    new Paragraph({
      border: {
        bottom: {
          color: "CCCCCC",
          space: 1,
          style: BorderStyle.SINGLE,
          size: 12,
        },
      },
      spacing: { after: 400 },
    })
  );

  // ========== SECTIONS ==========
  if (data.sections && Array.isArray(data.sections)) {
    data.sections.forEach((section, idx) => {
      if (section.heading) {
        children.push(
          new Paragraph({
            text: section.heading,
            heading: HeadingLevel.HEADING_1,
            spacing: { before: 300, after: 200 },
          })
        );
      }

      if (section.content) {
        addSectionContent(children, section.content);
      }

      // Spacing between sections
      if (idx < data.sections.length - 1) {
        children.push(
          new Paragraph({
            spacing: { after: 200 },
          })
        );
      }
    });
  }

  // ========== FINANCIALS ==========
  if (data.financials) {
    children.push(
      new Paragraph({
        text: "Financial Overview",
        heading: HeadingLevel.HEADING_1,
        spacing: { before: 300, after: 200 },
      })
    );

    addFinancials(children, data.financials, currency);
  }

  // ========== RISKS ==========
  if (data.risks && Array.isArray(data.risks) && data.risks.length > 0) {
    children.push(
      new Paragraph({
        text: "Risk Analysis",
        heading: HeadingLevel.HEADING_1,
        spacing: { before: 300, after: 200 },
      })
    );

    data.risks.forEach((risk, idx) => {
      const riskText =
        typeof risk === "string"
          ? risk
          : risk.risk || risk.description || JSON.stringify(risk);
      children.push(
        new Paragraph({
          children: [
            new TextRun({
              text: `⚠️ ${riskText}`,
              color: "DC2626",
            }),
          ],
          spacing: { after: 150 },
        })
      );
    });

    children.push(
      new Paragraph({
        spacing: { after: 200 },
      })
    );
  }

  // ========== OPPORTUNITIES ==========
  if (
    data.opportunities &&
    Array.isArray(data.opportunities) &&
    data.opportunities.length > 0
  ) {
    children.push(
      new Paragraph({
        text: "Opportunities",
        heading: HeadingLevel.HEADING_1,
        spacing: { before: 300, after: 200 },
      })
    );

    data.opportunities.forEach((opp, idx) => {
      const oppText =
        typeof opp === "string"
          ? opp
          : opp.opportunity || opp.description || JSON.stringify(opp);
      children.push(
        new Paragraph({
          text: `${idx + 1}. ${oppText}`,
          spacing: { after: 150 },
          bullet: { level: 0 },
        })
      );
    });

    children.push(
      new Paragraph({
        spacing: { after: 200 },
      })
    );
  }

  // ========== MANAGEMENT & CULTURE ==========
  if (data.management) {
    children.push(
      new Paragraph({
        text: "Management & Culture",
        heading: HeadingLevel.HEADING_1,
        spacing: { before: 300, after: 200 },
      })
    );

    if (data.management.summary) {
      children.push(
        new Paragraph({
          text: data.management.summary,
          spacing: { after: 200 },
        })
      );
    }

    // Strengths
    if (data.management.strengths && data.management.strengths.length > 0) {
      children.push(
        new Paragraph({
          text: "Strengths",
          heading: HeadingLevel.HEADING_2,
          spacing: { before: 200, after: 100 },
        })
      );

      data.management.strengths.forEach((strength) => {
        children.push(
          new Paragraph({
            text: `• ${strength}`,
            spacing: { after: 100 },
          })
        );
      });
    }

    // Gaps
    if (data.management.gaps && data.management.gaps.length > 0) {
      children.push(
        new Paragraph({
          text: "Gaps",
          heading: HeadingLevel.HEADING_2,
          spacing: { before: 200, after: 100 },
        })
      );

      data.management.gaps.forEach((gap) => {
        children.push(
          new Paragraph({
            text: `• ${gap}`,
            spacing: { after: 100 },
          })
        );
      });
    }

    children.push(
      new Paragraph({
        spacing: { after: 200 },
      })
    );
  }

  // ========== ESG SNAPSHOT ==========
  if (data.esg) {
    children.push(
      new Paragraph({
        text: "ESG Snapshot",
        heading: HeadingLevel.HEADING_1,
        spacing: { before: 300, after: 200 },
      })
    );

    // ESG Factors
    if (
      data.esg.factors &&
      Array.isArray(data.esg.factors) &&
      data.esg.factors.length > 0
    ) {
      data.esg.factors.forEach((factor) => {
        children.push(
          new Paragraph({
            children: [
              new TextRun({
                text: `${factor.dimension || "Factor"}: `,
                bold: true,
              }),
              new TextRun({
                text: factor.status || "N/A",
                color:
                  factor.status === "Positive"
                    ? "059669"
                    : factor.status === "Negative"
                    ? "DC2626"
                    : "6B7280",
              }),
            ],
            spacing: { after: 100 },
          })
        );
      });
    }

    // Overall ESG Summary
    if (data.esg.overall) {
      children.push(
        new Paragraph({
          text: data.esg.overall,
          spacing: { before: 150, after: 200 },
        })
      );
    }

    children.push(
      new Paragraph({
        spacing: { after: 200 },
      })
    );
  }

  // ========== NEXT STEPS ==========
  if (
    data.next_steps &&
    Array.isArray(data.next_steps) &&
    data.next_steps.length > 0
  ) {
    children.push(
      new Paragraph({
        text: "Next Steps",
        heading: HeadingLevel.HEADING_1,
        spacing: { before: 300, after: 200 },
      })
    );

    data.next_steps.forEach((step, idx) => {
      const stepText =
        typeof step === "string"
          ? step
          : step.step || step.action || JSON.stringify(step);
      children.push(
        new Paragraph({
          text: `${idx + 1}. ${stepText}`,
          spacing: { after: 100 },
          bullet: { level: 0 },
        })
      );
    });

    children.push(
      new Paragraph({
        spacing: { after: 200 },
      })
    );
  }

  // ========== INCONSISTENCIES ==========
  if (
    data.inconsistencies &&
    Array.isArray(data.inconsistencies) &&
    data.inconsistencies.length > 0
  ) {
    children.push(
      new Paragraph({
        text: "Inconsistencies Found",
        heading: HeadingLevel.HEADING_1,
        spacing: { before: 300, after: 200 },
      })
    );

    data.inconsistencies.forEach((item) => {
      const itemText =
        typeof item === "string"
          ? item
          : item.inconsistency || item.description || JSON.stringify(item);
      children.push(
        new Paragraph({
          children: [
            new TextRun({
              text: `⚠️ ${itemText}`,
              color: "D97706",
            }),
          ],
          spacing: { after: 100 },
        })
      );
    });

    children.push(
      new Paragraph({
        spacing: { after: 200 },
      })
    );
  }

  // ========== FOOTER ==========
  children.push(
    new Paragraph({
      border: {
        top: {
          color: "CCCCCC",
          space: 1,
          style: BorderStyle.SINGLE,
          size: 6,
        },
      },
      spacing: { before: 400, after: 200 },
    }),

    new Paragraph({
      text: "This is a confidential document prepared for investment evaluation purposes.",
      alignment: AlignmentType.CENTER,
      spacing: { after: 100 },
    }),

    new Paragraph({
      text: "Generated using AI-powered workflow analysis from document intelligence.",
      alignment: AlignmentType.CENTER,
      spacing: { after: 200 },
    }),

    new Paragraph({
      children: [
        new TextRun({
          text: "Generated by Sand Cloud Document Intelligence",
          italics: true,
          size: 18,
          color: "6B7280",
        }),
      ],
      alignment: AlignmentType.CENTER,
    })
  );

  // Create document
  const doc = new Document({
    sections: [
      {
        properties: {},
        children,
      },
    ],
  });

  // Generate and download
  const blob = await Packer.toBlob(doc);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = sanitizeFilename(`${companyName}_Investment_Memo.docx`);
  a.click();
  URL.revokeObjectURL(url);
}

/**
 * Add section content (handles strings, arrays, objects)
 * Parses markdown formatting and converts to Word elements
 */
function addSectionContent(children, content) {
  if (!content) return;

  if (typeof content === "string") {
    parseMarkdownContent(children, content);
  } else if (Array.isArray(content)) {
    content.forEach((item) => {
      if (typeof item === "string") {
        parseMarkdownContent(children, item);
      } else if (typeof item === "object") {
        addObjectContent(children, item);
      }
    });
  } else if (typeof content === "object") {
    addObjectContent(children, content);
  }
}

/**
 * Parse markdown content and convert to Word elements
 */
function parseMarkdownContent(children, text) {
  if (!text || typeof text !== "string") return;

  // Split into lines
  const lines = text.split("\n");
  let i = 0;

  while (i < lines.length) {
    const line = lines[i].trim();

    if (!line) {
      i++;
      continue;
    }

    // Check for headings (### Heading)
    const headingMatch = line.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const headingText = headingMatch[2];
      children.push(
        new Paragraph({
          text: headingText,
          heading:
            level === 1
              ? HeadingLevel.HEADING_1
              : level === 2
              ? HeadingLevel.HEADING_2
              : HeadingLevel.HEADING_3,
          spacing: { before: 200, after: 150 },
        })
      );
      i++;
      continue;
    }

    // Check for bullet list items (- item or * item)
    const bulletMatch = line.match(/^[-*]\s+(.+)$/);
    if (bulletMatch) {
      const bulletText = bulletMatch[1];
      children.push(
        new Paragraph({
          children: parseInlineMarkdown(bulletText),
          spacing: { after: 100 },
          bullet: { level: 0 },
        })
      );
      i++;
      continue;
    }

    // Check for numbered list items (1. item)
    const numberedMatch = line.match(/^(\d+)\.\s+(.+)$/);
    if (numberedMatch) {
      const numberedText = numberedMatch[2];
      children.push(
        new Paragraph({
          children: parseInlineMarkdown(numberedText),
          spacing: { after: 100 },
          bullet: { level: 0 },
        })
      );
      i++;
      continue;
    }

    // Regular paragraph - collect consecutive non-empty lines
    let paragraphText = line;
    i++;
    while (
      i < lines.length &&
      lines[i].trim() &&
      !lines[i].trim().match(/^(#{1,6}\s|[-*]\s|\d+\.\s)/)
    ) {
      paragraphText += "\n" + lines[i].trim();
      i++;
    }

    children.push(
      new Paragraph({
        children: parseInlineMarkdown(paragraphText),
        spacing: { after: 150 },
      })
    );
  }
}

/**
 * Parse inline markdown (bold, italics) and return TextRun array
 */
function parseInlineMarkdown(text) {
  if (!text) return [new TextRun({ text: "" })];

  const runs = [];
  let currentText = "";
  let i = 0;

  while (i < text.length) {
    // Check for bold (**text**)
    if (text[i] === "*" && text[i + 1] === "*") {
      // Save any accumulated text
      if (currentText) {
        runs.push(new TextRun({ text: currentText }));
        currentText = "";
      }

      // Find closing **
      const closeIndex = text.indexOf("**", i + 2);
      if (closeIndex !== -1) {
        const boldText = text.substring(i + 2, closeIndex);
        runs.push(new TextRun({ text: boldText, bold: true }));
        i = closeIndex + 2;
        continue;
      }
    }

    // Check for italics (*text*)
    if (text[i] === "*" && text[i + 1] !== "*") {
      // Save any accumulated text
      if (currentText) {
        runs.push(new TextRun({ text: currentText }));
        currentText = "";
      }

      // Find closing *
      const closeIndex = text.indexOf("*", i + 1);
      if (closeIndex !== -1 && text[closeIndex + 1] !== "*") {
        const italicText = text.substring(i + 1, closeIndex);
        runs.push(new TextRun({ text: italicText, italics: true }));
        i = closeIndex + 1;
        continue;
      }
    }

    // Regular character
    currentText += text[i];
    i++;
  }

  // Add any remaining text
  if (currentText) {
    runs.push(new TextRun({ text: currentText }));
  }

  return runs.length > 0 ? runs : [new TextRun({ text: text })];
}

/**
 * Add object content as key-value pairs
 */
function addObjectContent(children, obj) {
  if (!obj || typeof obj !== "object") return;

  Object.entries(obj).forEach(([key, value]) => {
    if (value === null || value === undefined || value === "") return;

    let displayValue;
    if (typeof value === "object" && !Array.isArray(value)) {
      displayValue = JSON.stringify(value, null, 2);
    } else if (Array.isArray(value)) {
      displayValue = value.join(", ");
    } else {
      displayValue = String(value);
    }

    children.push(
      new Paragraph({
        children: [
          new TextRun({
            text: `${formatKeyName(key)}: `,
            bold: true,
          }),
          new TextRun({
            text: displayValue,
          }),
        ],
        spacing: { after: 100 },
      })
    );
  });
}

/**
 * Add financials section with formatted data
 */
function addFinancials(children, financials, currency) {
  if (!financials || typeof financials !== "object") return;

  Object.entries(financials).forEach(([key, value]) => {
    if (value === null || value === undefined || value === "") return;

    let displayValue;
    if (typeof value === "number") {
      // Format as currency or number
      if (
        key.toLowerCase().includes("revenue") ||
        key.toLowerCase().includes("cost") ||
        key.toLowerCase().includes("profit")
      ) {
        displayValue = `${currency} ${value.toLocaleString()}`;
      } else if (
        key.toLowerCase().includes("margin") ||
        key.toLowerCase().includes("rate") ||
        key.toLowerCase().includes("%")
      ) {
        displayValue = `${value}%`;
      } else {
        displayValue = value.toLocaleString();
      }
    } else if (typeof value === "object" && !Array.isArray(value)) {
      displayValue = JSON.stringify(value, null, 2);
    } else if (Array.isArray(value)) {
      displayValue = value.join(", ");
    } else {
      displayValue = String(value);
    }

    children.push(
      new Paragraph({
        children: [
          new TextRun({
            text: `${formatKeyName(key)}: `,
            bold: true,
          }),
          new TextRun({
            text: displayValue,
          }),
        ],
        spacing: { after: 100 },
      })
    );
  });
}

/**
 * Format key name for display
 */
function formatKeyName(key) {
  return key.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase());
}

/**
 * Sanitize filename for safe download
 */
function sanitizeFilename(filename) {
  return filename
    .replace(/[^a-z0-9.-]/gi, "_")
    .replace(/_+/g, "_")
    .substring(0, 50)
    .toLowerCase();
}
