function truncate(value, maxLength) {
    if (!value) return "";
    const text = String(value);
    if (!maxLength || text.length <= maxLength) return text;
    return text.slice(0, maxLength);
}

function formatList(values) {
    if (!values || values.length === 0) return "(none)";
    return values.map((value) => `- ${value}`).join("\n");
}

function formatObjects(list, nameField, fields) {
    if (!list || list.length === 0) return "(none)";
    return list.map((item) => {
        const name = item?.[nameField] || "unknown";
        const lines = [`- ${name}`];
        for (const field of fields) {
            if (item?.[field] !== undefined) {
                lines.push(`  ${field}: ${JSON.stringify(item[field])}`);
            }
        }
        return lines.join("\n");
    }).join("\n");
}

const JOBS = {
    analysis: {
        id: "analysis",
        description: "General analysis with flexible output formatting.",
        system: [
            "You are a senior analyst.",
            "Follow the user's instructions exactly.",
            "If a specific format is requested, use it precisely.",
            "If no format is specified, use sections: Summary, Analysis, Risks/Assumptions, Recommendations.",
            "Be precise, avoid speculation, and flag uncertainty explicitly.",
            "Do not invent facts."
        ].join("\n"),
        buildPrompt: ({ prompt, task, input }) => {
            if (prompt) return String(prompt).trim();
            const cleanTask = String(task || "").trim();
            const cleanInput = String(input || "").trim();
            if (cleanInput) {
                return `Task:\n${cleanTask}\n\nInput:\n${cleanInput}`.trim();
            }
            return cleanTask;
        }
    },
    chat: {
        id: "chat",
        description: "General chat assistant for interactive conversations.",
        system: [
            "You are QuBot's professional assistant.",
            "Be clear, accurate, and concise by default.",
            "Ask a clarifying question when the request is ambiguous or missing key details.",
            "Provide actionable guidance and cite assumptions when needed.",
            "Match the user's tone without being overly casual."
        ].join("\n"),
        buildPrompt: ({ message }) => String(message || "").trim()
    },
    summarize: {
        id: "summarize",
        description: "Summarize text while preserving key facts and tone.",
        system: [
            "You are a professional summarizer.",
            "Preserve key facts, names, numbers, and intent.",
            "Maintain the original tone.",
            "Do not add new information.",
            "Output plain text only."
        ].join("\n"),
        buildPrompt: ({ text, maxLength }) => {
            const content = truncate(text, 5000);
            const limit = Number.isFinite(maxLength) ? maxLength : 200;
            return [
                `Summarize the following text in ${limit} characters or less.`,
                "Be concise and capture the key points.",
                "If the text includes steps or action items, keep them.",
                "",
                content
            ].join("\n").trim();
        }
    },
    translate: {
        id: "translate",
        description: "Translate text between languages.",
        system: [
            "You are a professional translator.",
            "Preserve meaning, tone, and formatting.",
            "Keep proper nouns and product names unchanged unless commonly translated.",
            "Do not translate code, commands, or URLs.",
            "Output only the translation."
        ].join("\n"),
        buildPrompt: ({ text, targetLanguage, sourceLanguage }) => {
            const sourcePart = sourceLanguage ? `from ${sourceLanguage} ` : "";
            const target = targetLanguage || "the requested language";
            const content = truncate(text, 6000);
            return `Translate the following text ${sourcePart}to ${target}.\n\nText:\n${content}`.trim();
        }
    },
    language_learning: {
        id: "language_learning",
        description: "Language tutoring with corrections, explanations, and practice.",
        system: [
            "You are a language tutor.",
            "Keep explanations clear and level-appropriate.",
            "Use sections: Corrections, Explanation, Improved Version, Practice.",
            "In Corrections, show original -> corrected.",
            "Provide 2-4 practice items aligned with the learner's goal."
        ].join("\n"),
        buildPrompt: ({ text, targetLanguage, level, goal }) => {
            const content = truncate(text, 3000);
            const levelLabel = level || "intermediate";
            const goalLabel = goal || "general improvement";
            return [
                "Learner profile:",
                `- Target language: ${targetLanguage || "unspecified"}`,
                `- Level: ${levelLabel}`,
                `- Goal: ${goalLabel}`,
                "",
                "Learner input:",
                content
            ].join("\n").trim();
        }
    },
    research: {
        id: "research",
        description: "Research brief with cautious sourcing.",
        system: [
            "You are a research assistant.",
            "Use only the provided sources if present.",
            "If sources are missing for a claim, say so.",
            "Avoid speculation; mark uncertainty clearly.",
            "Respond with sections: Summary, Key Points, Evidence, Open Questions, Next Steps."
        ].join("\n"),
        buildPrompt: ({ question, sources }) => {
            const sourceLines = Array.isArray(sources) ? sources.map((s) => `- ${s}`).join("\n") : "(none)";
            return [
                `Research question: ${question}`,
                "",
                "Sources:",
                sourceLines
            ].join("\n").trim();
        }
    },
    coding_tool_use: {
        id: "coding_tool_use",
        description: "Plan tool usage for coding tasks with structured output.",
        system: [
            "You are a coding assistant that plans tool usage.",
            "Do not execute tools.",
            "Return JSON only.",
            "Use keys: plan, tool_calls, final_note.",
            "tool_calls items must include tool and input.",
            "If no tool is needed, return empty arrays."
        ].join("\n"),
        buildPrompt: ({ task, tools, constraints }) => {
            const toolBlock = formatObjects(tools, "name", ["description", "inputSchema"]);
            return [
                `Task: ${task}`,
                "",
                "Available tools:",
                toolBlock,
                "",
                `Constraints: ${constraints || "(none)"}`,
                "",
                "Return JSON only:",
                "{\"plan\":[\"step 1\"],\"tool_calls\":[{\"tool\":\"tool_name\",\"input\":{}}],\"final_note\":\"short note\"}"
            ].join("\n").trim();
        }
    },
    function_call: {
        id: "function_call",
        description: "Select a function and return arguments as JSON.",
        system: [
            "You are a function calling router.",
            "Choose the best function from the list.",
            "Return JSON only in the specified format.",
            "If no function applies, return name 'none' with empty arguments.",
            "Do not include additional keys."
        ].join("\n"),
        buildPrompt: ({ task, functions }) => {
            const functionBlock = formatObjects(functions, "name", ["description", "parameters"]);
            return [
                `User request: ${task}`,
                "",
                "Available functions:",
                functionBlock,
                "",
                "Return JSON only:",
                "{\"name\":\"function_name\",\"arguments\":{}}"
            ].join("\n").trim();
        }
    },
    claude_skill: {
        id: "claude_skill",
        description: "Select a Claude skill and return structured input.",
        system: [
            "You are a skill router.",
            "Choose the best skill from the list.",
            "Return JSON only in the specified format.",
            "If no skill applies, return skill 'none' with empty input.",
            "Do not include additional keys."
        ].join("\n"),
        buildPrompt: ({ task, skills }) => {
            const skillBlock = formatObjects(skills, "name", ["description", "inputSchema"]);
            return [
                `User request: ${task}`,
                "",
                "Available skills:",
                skillBlock,
                "",
                "Return JSON only:",
                "{\"skill\":\"skill_name\",\"input\":{}}"
            ].join("\n").trim();
        }
    },
    categorize: {
        id: "categorize",
        description: "Categorize text into predefined categories.",
        system: [
            "You are a classification assistant.",
            "Choose exactly one category from the provided list.",
            "Return JSON only in the specified format.",
            "If uncertain, choose the closest category and mark low confidence."
        ].join("\n"),
        buildPrompt: ({ text, categories }) => {
            const content = truncate(text, 2000);
            const categoryList = formatList(categories || []);
            return [
                "Categorize the following text into one of these categories:",
                categoryList,
                "",
                "Text:",
                content,
                "",
                "Return JSON only:",
                "{\"category\":\"chosen_category\",\"confidence\":\"high|medium|low\",\"reasoning\":\"brief explanation\"}"
            ].join("\n").trim();
        }
    },
    extract: {
        id: "extract",
        description: "Extract structured fields from text.",
        system: [
            "You extract structured data from text.",
            "Return JSON only with the requested fields.",
            "Use null when a field is not present.",
            "Preserve exact wording for names, numbers, and identifiers."
        ].join("\n"),
        buildPrompt: ({ text, fields }) => {
            const content = truncate(text, 3000);
            const fieldList = formatList(fields || []);
            return [
                "Extract the following fields from the text:",
                fieldList,
                "",
                "Text:",
                content,
                "",
                "Return JSON only with the requested fields."
            ].join("\n").trim();
        }
    },
    sentiment: {
        id: "sentiment",
        description: "Sentiment analysis with score.",
        system: [
            "You analyze sentiment.",
            "Use sentiment labels: positive, negative, neutral.",
            "Score ranges from -1 to 1 (negative to positive).",
            "Return JSON only in the specified format."
        ].join("\n"),
        buildPrompt: ({ text }) => {
            const content = truncate(text, 500);
            return [
                "Analyze the sentiment of this text.",
                "",
                "Text:",
                content,
                "",
                "Return JSON only:",
                "{\"sentiment\":\"positive|negative|neutral\",\"score\":-1}"
            ].join("\n").trim();
        }
    },
    smart_filter_match: {
        id: "smart_filter_match",
        description: "Semantic filter matching with confidence.",
        system: [
            "You compare a message against filter criteria.",
            "Match only when the message clearly satisfies the criteria.",
            "Return JSON only in the specified format."
        ].join("\n"),
        buildPrompt: ({ text, criteria }) => {
            const content = truncate(text, 1000);
            const criteriaText = criteria ? JSON.stringify(criteria) : "{}";
            return [
                "Analyze if this message matches the filter criteria.",
                "",
                "Message:",
                content,
                "",
                "Criteria:",
                criteriaText,
                "",
                "Return JSON only:",
                "{\"matches\":true,\"confidence\":\"high|medium|low\",\"reasoning\":\"brief explanation\"}"
            ].join("\n").trim();
        }
    },
    digest: {
        id: "digest",
        description: "Create a digest of multiple messages.",
        system: [
            "You summarize multiple messages into a short digest.",
            "Group by topic and highlight key information.",
            "Include source labels where relevant.",
            "Keep it concise and easy to scan."
        ].join("\n"),
        buildPrompt: ({ messages }) => {
            const lines = (messages || []).slice(0, 20).map((m, i) => {
                const source = m?.source || "unknown";
                const text = truncate(m?.text || "", 120);
                return `${i + 1}. [${source}] ${text}`;
            }).join("\n");
            return [
                "Create a brief digest of these messages.",
                "Use short topic headings and bullet points.",
                "",
                "Messages:",
                lines
            ].join("\n").trim();
        }
    },
    rank_relevance: {
        id: "rank_relevance",
        description: "Rank items by relevance to a query.",
        system: [
            "You rank items by relevance to the user's interest.",
            "Return JSON only in the specified format.",
            "Include every item index in the response."
        ].join("\n"),
        buildPrompt: ({ items, query }) => {
            const lines = (items || []).slice(0, 10).map((item, idx) => {
                const title = truncate(item?.title || item?.name || "", 120);
                return `${idx + 1}. ${title}`;
            }).join("\n");
            return [
                `User interest: ${query}`,
                "",
                "Rank these items by relevance (1-10, 10 = most relevant):",
                lines,
                "",
                "Return JSON only:",
                "[{\"index\":1,\"relevance\":8}]"
            ].join("\n").trim();
        }
    },
    chat_summary: {
        id: "chat_summary",
        description: "Short chat summary for context.",
        system: [
            "You summarize conversation context for future messages.",
            "Keep it to 2-3 sentences.",
            "Mention key topics, decisions, and open issues.",
            "Do not include extra commentary."
        ].join("\n"),
        buildPrompt: ({ messagesText }) => {
            return [
                "Summarize this conversation in 2-3 sentences:",
                "",
                messagesText
            ].join("\n").trim();
        }
    },
    chat_notes: {
        id: "chat_notes",
        description: "Structured knowledge summary for exported chats.",
        system: [
            "You extract all valuable knowledge from a conversation.",
            "Do not omit important details, decisions, or action items.",
            "Preserve names, numbers, commands, and URLs exactly.",
            "If the conversation contains conflicting statements, list both.",
            "Use clear section headers and bullet points.",
            "If a section has no data, write \"None\"."
        ].join("\n"),
        buildPrompt: ({ conversation }) => {
            const content = truncate(conversation, 15000);
            return [
                "Create a structured knowledge summary with these sections:",
                "## Summary",
                "## Key Facts and Concepts",
                "## Decisions and Conclusions",
                "## Action Items and Next Steps",
                "## Code and Commands",
                "## References and Links",
                "## Open Questions",
                "",
                "Capture all valuable knowledge mentioned in the conversation.",
                "Use bullet points inside sections, and code blocks for code/commands.",
                "",
                "Conversation:",
                content
            ].join("\n").trim();
        }
    }
};

function getJobDefinition(jobId) {
    return JOBS[jobId] || null;
}

function listJobs() {
    return Object.values(JOBS).map(({ id, description }) => ({ id, description }));
}

function buildJobPrompt(jobId, payload = {}) {
    const job = getJobDefinition(jobId);
    if (!job) {
        throw new Error(`Unknown AI job: ${jobId}`);
    }

    const prompt = job.buildPrompt ? job.buildPrompt(payload) : String(payload?.prompt || "").trim();
    if (!prompt) {
        throw new Error(`Empty prompt for AI job: ${jobId}`);
    }

    return {
        system: job.system || "",
        prompt
    };
}

module.exports = {
    buildJobPrompt,
    getJobDefinition,
    listJobs,
};
