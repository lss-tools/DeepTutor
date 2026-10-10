"use client";

import {
  AudioLines,
  Bot,
  Boxes,
  Brain,
  BrainCircuit,
  Clapperboard,
  Database,
  FileScan,
  FolderOpen,
  Image as ImageIcon,
  Info,
  KeyRound,
  Library,
  ListChecks,
  MessagesSquare,
  Mic,
  Network,
  Palette,
  Paperclip,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  ChartNoAxesCombined,
  UserRound,
  Wrench,
  type LucideIcon,
} from "lucide-react";

import {
  ClaudeGlyph,
  CodexGlyph,
  DeepSeekGlyph,
  GeminiGlyph,
  GrokGlyph,
  HermesGlyph,
  KimiGlyph,
  MimoGlyph,
  OpenClawGlyph,
  OpencodeGlyph,
} from "@/components/agents/agent-icons";
import type { ServiceName } from "@/features/settings/store/SettingsStore";
import type { SettingsAccess } from "@/features/settings/navigation/settings-access";

/**
 * Settings information architecture.
 *
 * Independent settings pages, with legacy fragment aliases preserved.
 * This module remains the source for labels, visibility,
 * search metadata, and persistence hints.
 */

export type Lang = { zh: string; en: string; ru: string };

export interface SettingsLeaf {
  key: string;
  href: string;
  label: Lang;
  blurb: Lang;
  icon: LucideIcon;
  /** Colored icon-tile accent for the sub-hub grid (full class strings). */
  tile: string;
  /** Model-service leaves carry a configured/not chip from the catalog. */
  service?: ServiceName;
  /** Hidden from non-admin users (the backend rejects them anyway). */
  adminOnly?: boolean;
}

export interface SettingsCategory {
  key: string;
  label: Lang;
  /** One-line descriptor shown on the hub block. */
  blurb: Lang;
  icon: LucideIcon;
  /** Canonical in-document category anchor. */
  href: string;
  /** Nested anchors (omitted for direct-section categories). */
  children?: SettingsLeaf[];
  /** Shown only when the backend reports an active learner policy. */
  learnerOnly?: boolean;
  /** Shown only to authenticated standard users who may act as guardians. */
  guardianOnly?: boolean;
}

export function isSettingsLeafVisible(
  leaf: SettingsLeaf,
  access: SettingsAccess,
): boolean {
  return !(leaf.adminOnly && access.hideAdminOnly);
}

export function isSettingsCategoryVisible(
  category: SettingsCategory,
  access: SettingsAccess,
): boolean {
  if (category.learnerOnly && !access.showLearnerOnly) return false;
  if (category.guardianOnly && !access.showGuardianOnly) return false;
  return (
    !category.children ||
    category.children.some((leaf) => isSettingsLeafVisible(leaf, access))
  );
}

export function visibleSettingsChildren(
  categoryKey: string,
  access: SettingsAccess,
): SettingsLeaf[] {
  return (
    SETTINGS_CATEGORIES.find((category) => category.key === categoryKey)
      ?.children ?? []
  ).filter((leaf) => isSettingsLeafVisible(leaf, access));
}

const MODEL_CHILDREN: SettingsLeaf[] = [
  {
    key: "voice",
    href: "/settings/voice",
    label: { en: "Voice", zh: "语音", ru: "Голос" },
    blurb: {
      en: "Speech synthesis and transcription models with saved providers.",
      zh: "使用已配置的提供方管理语音合成与语音识别模型。",
      ru: "Модели синтеза и распознавания речи с сохранёнными провайдерами.",
    },
    icon: AudioLines,
    tile: "bg-rose-500/10 text-rose-600",
  },
  {
    key: "multimodal",
    href: "/settings/multimodal",
    label: { en: "Multimodal generation", zh: "多模态生成", ru: "Мультимодальная генерация" },
    blurb: {
      en: "Image and video generation models with saved providers.",
      zh: "使用已配置的提供方管理图片与视频生成模型。",
      ru: "Модели генерации картинок и видео с сохранёнными провайдерами.",
    },
    icon: ImageIcon,
    tile: "bg-violet-500/10 text-violet-600",
  },
  {
    key: "connections",
    href: "/settings#connections",
    label: { zh: "提供方", en: "Providers", ru: "Провайдеры" },
    blurb: {
      zh: "管理提供方的名称、地址、密钥并测试连接。",
      en: "Manage provider names, addresses, credentials, and connectivity.",
      ru: "Имена, адреса и ключи провайдеров, проверка соединения.",
    },
    icon: KeyRound,
    tile: "bg-sky-500/10 text-sky-600 dark:text-sky-400",
  },
  {
    key: "llm",
    href: "/settings#llm",
    label: { zh: "语言模型", en: "Language models", ru: "Языковые модели" },
    blurb: {
      zh: "模型名称、上下文窗口、能力与连接测试。",
      en: "Model names, context windows, capabilities, and connection tests.",
      ru: "Названия моделей, контексты, возможности и проверка соединения.",
    },
    icon: Brain,
    tile: "bg-violet-500/10 text-violet-600 dark:text-violet-400",
    service: "llm",
  },
  {
    key: "task-models",
    href: "/settings#task-models",
    label: { zh: "后台任务模型", en: "Task models", ru: "Модели задач" },
    blurb: {
      zh: "DeepTutor 自己发起的调用使用的模型。",
      en: "The model behind the calls DeepTutor makes on its own.",
      ru: "Модель для вызовов, которые DeepTutor делает сам.",
    },
    icon: ListChecks,
    tile: "bg-cyan-500/10 text-cyan-600 dark:text-cyan-400",
  },
  {
    key: "embedding",
    href: "/settings#embedding",
    label: { zh: "嵌入模型", en: "Embedding models", ru: "Эмбеддинг-модели" },
    blurb: {
      zh: "嵌入模型、维度与连接测试。",
      en: "Embedding models, dimensions, and connection tests.",
      ru: "Эмбеддинг-модели, размерности и проверка соединения.",
    },
    icon: Database,
    tile: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
    service: "embedding",
  },
  {
    key: "search",
    href: "/settings#search",
    label: { zh: "搜索", en: "Search", ru: "Поиск" },
    blurb: { zh: "联网搜索供应商。", en: "Web search providers.", ru: "Провайдеры веб-поиска." },
    icon: Search,
    tile: "bg-amber-500/10 text-amber-600 dark:text-amber-400",
    service: "search",
  },
  {
    key: "tts",
    href: "/settings#tts",
    label: { zh: "语音合成", en: "Text-to-Speech", ru: "Синтез речи" },
    blurb: {
      zh: "朗读助手回复的 TTS 供应商。",
      en: "Text-to-speech for reading replies aloud.",
      ru: "Синтез речи для чтения ответов вслух.",
    },
    icon: AudioLines,
    tile: "bg-rose-500/10 text-rose-600 dark:text-rose-400",
    service: "tts",
  },
  {
    key: "stt",
    href: "/settings#stt",
    label: { zh: "语音识别", en: "Speech-to-Text", ru: "Распознавание речи" },
    blurb: {
      zh: "转写麦克风录音的 STT 供应商。",
      en: "Transcribes microphone recordings for the composer microphone.",
      ru: "Распознаёт записи с микрофона для поля ввода.",
    },
    icon: Mic,
    tile: "bg-pink-500/10 text-pink-600 dark:text-pink-400",
    service: "stt",
  },
  {
    key: "imagegen",
    href: "/settings#imagegen",
    label: { zh: "文生图", en: "Image Generation", ru: "Генерация картинок" },
    blurb: {
      zh: "chat imagegen 工具使用的文生图模型。",
      en: "Text-to-image model for the chat imagegen tool.",
      ru: "Модель текст-в-картинку для инструмента imagegen в чате.",
    },
    icon: ImageIcon,
    tile: "bg-fuchsia-500/10 text-fuchsia-600 dark:text-fuchsia-400",
    service: "imagegen",
  },
  {
    key: "videogen",
    href: "/settings#videogen",
    label: { zh: "文生视频", en: "Video Generation", ru: "Генерация видео" },
    blurb: {
      zh: "chat videogen 工具使用的文生视频模型。",
      en: "Text-to-video model for the chat videogen tool.",
      ru: "Модель текст-в-видео для инструмента videogen в чате.",
    },
    icon: Clapperboard,
    tile: "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400",
    service: "videogen",
  },
];

const CHAT_CHILDREN: SettingsLeaf[] = [
  {
    key: "video-learning",
    href: "/settings#video-learning",
    label: { zh: "视频学习", en: "Video Learning", ru: "Видеообучение" },
    blurb: {
      zh: "原生 YouTube 与本地 Invidious 播放供应商。",
      en: "Native YouTube and local Invidious playback providers.",
      ru: "Штатный YouTube и локальные провайдеры Invidious.",
    },
    icon: Clapperboard,
    tile: "bg-red-500/10 text-red-600 dark:text-red-400",
    adminOnly: true,
  },
  {
    key: "tools",
    href: "/settings#tools",
    label: { zh: "工具", en: "Tools", ru: "Инструменты" },
    blurb: {
      zh: "对话智能体可调用的内置工具。",
      en: "Built-in tools the chat agent can invoke.",
      ru: "Встроенные инструменты агента чата.",
    },
    icon: Wrench,
    tile: "bg-orange-500/10 text-orange-600 dark:text-orange-400",
  },
  {
    key: "capabilities",
    href: "/settings#capabilities",
    label: { zh: "能力", en: "Capabilities", ru: "Возможности" },
    blurb: {
      zh: "各能力的 LLM 参数与运行时旋钮。",
      en: "Per-capability LLM parameters and runtime knobs.",
      ru: "Параметры LLM и настройки для каждой возможности.",
    },
    icon: SlidersHorizontal,
    tile: "bg-lime-500/10 text-lime-600 dark:text-lime-400",
  },
  {
    key: "starters",
    href: "/settings#starters",
    label: { zh: "起始建议", en: "Starting points", ru: "Стартовые подсказки" },
    blurb: {
      zh: "主页输入框下方那三行引导的素材范围。",
      en: "How much history shapes the three lines under the composer.",
      ru: "Насколько история влияет на три строки под полем ввода.",
    },
    icon: Sparkles,
    tile: "bg-violet-500/10 text-violet-600 dark:text-violet-400",
  },
  {
    key: "attachments",
    href: "/settings#attachments",
    label: { zh: "附件", en: "Attachments", ru: "Вложения" },
    blurb: {
      zh: "聊天附件的大小上限与文本提取预算。",
      en: "Upload caps and extraction budgets for chat attachments.",
      ru: "Лимиты загрузки и бюджеты извлечения текста для вложений чата.",
    },
    icon: Paperclip,
    tile: "bg-teal-500/10 text-teal-600 dark:text-teal-400",
    adminOnly: true,
  },
];

const AGENT_CHILDREN: SettingsLeaf[] = [
  {
    key: "agent-claude-code",
    href: "/settings#agent-claude-code",
    label: { zh: "Claude Code", en: "Claude Code", ru: "Claude Code" },
    blurb: {
      zh: "DeepTutor 调用本机 Claude Code 时的模型、推理强度与运行参数。",
      en: "Model, reasoning effort, and run params for the local Claude Code.",
      ru: "Модель, сила рассуждений и параметры запуска локального Claude Code.",
    },
    // Brand glyph shares the lucide call signature (size/className).
    icon: ClaudeGlyph as unknown as LucideIcon,
    tile: "bg-orange-500/10 text-orange-600 dark:text-orange-400",
    adminOnly: true,
  },
  {
    key: "agent-codex",
    href: "/settings#agent-codex",
    label: { zh: "Codex", en: "Codex", ru: "Codex" },
    blurb: {
      zh: "DeepTutor 调用本机 Codex 时的模型、推理强度与运行参数。",
      en: "Model, reasoning effort, and run params for the local Codex.",
      ru: "Модель, сила рассуждений и параметры запуска локального Codex.",
    },
    icon: CodexGlyph as unknown as LucideIcon,
    tile: "bg-blue-500/10 text-blue-600 dark:text-blue-400",
    adminOnly: true,
  },
  {
    key: "agent-grok",
    href: "/settings#agent-grok",
    label: { zh: "Grok CLI", en: "Grok CLI", ru: "Grok CLI" },
    blurb: {
      zh: "DeepTutor 调用本机 Grok CLI 时的模型、推理强度与权限模式。",
      en: "Model, reasoning effort, and permission mode for the local Grok CLI.",
      ru: "Модель, сила рассуждений и режим прав локального Grok CLI.",
    },
    icon: GrokGlyph as unknown as LucideIcon,
    tile: "bg-zinc-500/10 text-zinc-700 dark:text-zinc-300",
    adminOnly: true,
  },
  {
    // Gemini CLI's supported replacement.
    key: "agent-antigravity",
    href: "/settings#agent-antigravity",
    label: { zh: "Antigravity CLI", en: "Antigravity CLI", ru: "Antigravity CLI" },
    blurb: {
      zh: "DeepTutor 调用本机 Antigravity CLI 时的模型与运行参数。",
      en: "Model and run params for the local Antigravity CLI.",
      ru: "Модель и параметры запуска локального Antigravity CLI.",
    },
    icon: GeminiGlyph as unknown as LucideIcon,
    tile: "bg-sky-500/10 text-sky-600 dark:text-sky-400",
    adminOnly: true,
  },
  {
    key: "agent-kimi",
    href: "/settings#agent-kimi",
    label: { zh: "Kimi CLI", en: "Kimi CLI", ru: "Kimi CLI" },
    blurb: {
      zh: "DeepTutor 调用本机 Kimi CLI 时的模型与运行参数。",
      en: "Model and run params for the local Kimi CLI.",
      ru: "Модель и параметры запуска локального Kimi CLI.",
    },
    icon: KimiGlyph as unknown as LucideIcon,
    tile: "bg-zinc-500/10 text-zinc-700 dark:text-zinc-300",
    adminOnly: true,
  },
  {
    key: "agent-opencode",
    href: "/settings#agent-opencode",
    label: { zh: "opencode", en: "opencode", ru: "opencode" },
    blurb: {
      zh: "DeepTutor 调用本机 opencode 时的模型与运行参数。",
      en: "Model and run params for the local opencode.",
      ru: "Модель и параметры запуска локального opencode.",
    },
    icon: OpencodeGlyph as unknown as LucideIcon,
    tile: "bg-neutral-500/10 text-neutral-700 dark:text-neutral-300",
    adminOnly: true,
  },
  {
    key: "agent-mimo",
    href: "/settings#agent-mimo",
    label: { zh: "MiMo Code", en: "MiMo Code", ru: "MiMo Code" },
    blurb: {
      zh: "DeepTutor 调用本机 MiMo Code 时的模型与运行参数。",
      en: "Model and run params for the local MiMo Code.",
      ru: "Модель и параметры запуска локального MiMo Code.",
    },
    icon: MimoGlyph as unknown as LucideIcon,
    tile: "bg-orange-500/10 text-orange-600 dark:text-orange-400",
    adminOnly: true,
  },
  {
    key: "agent-hermes",
    href: "/settings#agent-hermes",
    label: { zh: "Hermes Agent", en: "Hermes Agent", ru: "Hermes Agent" },
    blurb: {
      zh: "DeepTutor 调用本机 Hermes Agent 时的模型、推理强度与运行参数。",
      en: "Model, reasoning effort, and run params for the local Hermes Agent.",
      ru: "Модель, сила рассуждений и параметры запуска локального Hermes Agent.",
    },
    icon: HermesGlyph as unknown as LucideIcon,
    tile: "bg-violet-500/10 text-violet-600 dark:text-violet-400",
    adminOnly: true,
  },
  {
    key: "agent-hermes-remote",
    href: "/settings#agent-hermes-remote",
    label: { zh: "Hermes Agent（远程）", en: "Hermes Agent (remote)", ru: "Hermes Agent (удалённый)" },
    blurb: {
      zh: "通过 HTTP 网关调用远程 Hermes Agent，并按会话保持上下文。",
      en: "Call a remote Hermes Agent over HTTP with per-chat session continuity.",
      ru: "Вызов удалённого Hermes Agent по HTTP с контекстом на каждый чат.",
    },
    icon: HermesGlyph as unknown as LucideIcon,
    tile: "bg-violet-500/10 text-violet-600 dark:text-violet-400",
    adminOnly: true,
  },
  {
    key: "agent-openclaw",
    href: "/settings#agent-openclaw",
    label: { zh: "OpenClaw", en: "OpenClaw", ru: "OpenClaw" },
    blurb: {
      zh: "DeepTutor 通过 Gateway 或本地模式调用 OpenClaw 的运行参数。",
      en: "Gateway or local-mode run params for the local OpenClaw agent.",
      ru: "Параметры запуска локального OpenClaw: шлюз или локальный режим.",
    },
    icon: OpenClawGlyph as unknown as LucideIcon,
    tile: "bg-red-500/10 text-red-600 dark:text-red-400",
    adminOnly: true,
  },
  {
    key: "agent-deepseek-harness",
    href: "/settings#agent-deepseek-harness",
    label: { zh: "DeepSeek Harness", en: "DeepSeek Harness", ru: "DeepSeek Harness" },
    blurb: {
      zh: "DeepTutor 通过 Python SDK 或 headless CLI 调用 DeepSeek Harness。",
      en: "Python SDK or headless CLI settings for DeepSeek Harness.",
      ru: "Настройки DeepSeek Harness: Python SDK или headless CLI.",
    },
    icon: DeepSeekGlyph as unknown as LucideIcon,
    tile: "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400",
    adminOnly: true,
  },
];

export const SETTINGS_CATEGORIES: SettingsCategory[] = [
  {
    key: "appearance",
    label: { zh: "外观", en: "Appearance", ru: "Оформление" },
    blurb: { zh: "视觉主题与代码块", en: "Theme and code blocks", ru: "Тема и блоки кода" },
    icon: Palette,
    href: "/settings#appearance",
  },
  {
    key: "network",
    label: { zh: "网络", en: "Network", ru: "Сеть" },
    blurb: {
      zh: "端口、浏览器 API 地址与 CORS",
      en: "Ports, browser API base, and CORS",
      ru: "Порты, адрес API браузера и CORS",
    },
    icon: Network,
    href: "/settings#network",
  },
  {
    key: "workspace",
    label: { zh: "工作区", en: "Workspace", ru: "Рабочее пространство" },
    blurb: {
      zh: "系统、通用与自建工作区，根目录与存储迁移",
      en: "System, general and custom workspaces, root folder and storage migration",
      ru: "Системные, общие и свои пространства, корневой каталог и перенос хранилища",
    },
    icon: FolderOpen,
    href: "/settings#workspace",
  },
  {
    key: "models",
    label: { zh: "模型", en: "Models", ru: "Модели" },
    blurb: {
      zh: "语言、向量、搜索、语音与生成模型",
      en: "Language, embedding, search, voice, and generation models",
      ru: "Языковые, эмбеддинг-, поисковые, голосовые и генеративные модели",
    },
    icon: Boxes,
    href: "/settings#models",
    children: MODEL_CHILDREN,
  },
  {
    key: "knowledge",
    label: { zh: "知识库", en: "Knowledge Base", ru: "База знаний" },
    blurb: { zh: "文档解析引擎", en: "Document parsing engine", ru: "Движок разбора документов" },
    icon: Library,
    href: "/settings#document-parsing",
  },
  {
    key: "chat",
    label: { zh: "聊天", en: "Chat", ru: "Чат" },
    blurb: {
      zh: "工具、能力与附件",
      en: "Tools, capabilities, and attachments",
      ru: "Инструменты, возможности и вложения",
    },
    icon: MessagesSquare,
    href: "/settings#chat",
    children: CHAT_CHILDREN,
  },
  {
    key: "agents",
    label: { zh: "伙伴和智能体", en: "Partners & Agents", ru: "Партнёры и агенты" },
    blurb: {
      zh: "配置可在对话中调用的子智能体",
      en: "Configure the subagents you can call on in chat",
      ru: "Настройка субагентов, которых можно вызывать в чате",
    },
    icon: Bot,
    href: "/settings#agents",
    children: AGENT_CHILDREN,
  },
  {
    key: "progress",
    label: { zh: "学习进度", en: "Learning progress", ru: "Учебный прогресс" },
    blurb: { zh: "查看自己的阅读与学习记录。", en: "Review your reading and learning activity.", ru: "Ваша активность в чтении и обучении." },
    icon: ChartNoAxesCombined,
    href: "/settings/progress",
  },
  {
    key: "learner-profile",
    learnerOnly: true,
    label: { zh: "学习档案", en: "Learner profile", ru: "Профиль ученика" },
    blurb: {
      zh: "调整年龄、年级与讲解偏好。",
      en: "Adjust age, grade, and explanation preferences.",
      ru: "Возраст, класс и предпочтения объяснений.",
    },
    icon: UserRound,
    href: "/settings#learner-profile",
  },
  {
    key: "guardian",
    guardianOnly: true,
    label: { zh: "监护管理", en: "Guardian", ru: "Опекун" },
    blurb: {
      zh: "查看已授权学习者与学习材料。",
      en: "Review authorized learners and learning materials.",
      ru: "Разрешённые ученики и учебные материалы.",
    },
    icon: ShieldCheck,
    href: "/settings#guardian",
  },
  {
    key: "memory",
    label: { zh: "记忆", en: "Memory", ru: "Память" },
    blurb: {
      zh: "分块、预算、去重与引用策略",
      en: "Chunking, budget, dedup, and reference policies",
      ru: "Нарезка, бюджет, дедупликация и политика цитирования",
    },
    icon: BrainCircuit,
    href: "/settings#memory",
  },
  {
    key: "about",
    label: { zh: "关于", en: "About", ru: "О программе" },
    blurb: {
      zh: "版本、更新与项目资源",
      en: "Version, updates, and project resources",
      ru: "Версия, обновления и ресурсы проекта",
    },
    icon: Info,
    href: "/settings#about",
  },
];

export const SETTINGS_HUB_HREF = "/settings";

/** Stable aliases keep existing bookmarks and links from older clients working. */
export const SETTINGS_ALIASES: Record<string, string> = {
  tts: "voice",
  stt: "voice",
  imagegen: "multimodal",
  videogen: "multimodal",
  overview: "general",
  models: "llm",
  chat: "starters",
  agents: "agent-claude-code",
  "document-parsing": "knowledge",
  image: "multimodal",
  video: "multimodal",
};

export function resolveSettingsKey(key: string): string {
  return SETTINGS_ALIASES[key] ?? key;
}

/** Kept as an API name for callers; URLs now address independent pages. */
export function settingsAnchorHref(key: string): string {
  return `${SETTINGS_HUB_HREF}/${resolveSettingsKey(key)}`;
}

// The on-disk file (under data/user/settings/) each leaf module persists to.
// Surfaced in the toolbar status line so every page says where its parameters
// live, without duplicating the string on each page. Singleton pages (no
// merged category) are keyed by pathname; leaves inside a merged category
// page share one pathname, so those are keyed by `leaf.key` instead and
// looked up via the currently scrolled-to section (see `storagePathFor`).
const STORAGE_PATHS: Record<string, string> = {
  "/settings#appearance": "data/user/settings/interface.json",
  "/settings#network": "data/user/settings/system.json",
  "/settings#workspace": "data/user/.runtime/workspaces.sqlite3",
  "/settings#llm": "data/user/settings/model_catalog.json",
  "/settings#embedding": "data/user/settings/model_catalog.json",
  "/settings#search": "data/user/settings/model_catalog.json",
  "/settings#tts": "data/user/settings/model_catalog.json",
  "/settings#stt": "data/user/settings/model_catalog.json",
  "/settings#image": "data/user/settings/model_catalog.json",
  "/settings#video": "data/user/settings/model_catalog.json",
  "/settings#video-learning": "data/user/settings/video_learning.json",
  "/settings#document-parsing": "data/user/settings/document_parsing.json",
  "/settings#memory": "data/user/settings/main.yaml",
  appearance: "data/user/settings/interface.json",
  network: "data/user/settings/system.json",
  workspace: "data/user/.runtime/workspaces.sqlite3",
  voice: "data/user/settings/model_catalog.json",
  multimodal: "data/user/settings/model_catalog.json",
  connections: "data/user/settings/model_catalog.json",
  "task-models": "data/user/settings/model_catalog.json",
  knowledge: "data/user/settings/document_parsing.json",
  "video-learning": "data/user/settings/video_learning.json",
  starters: "data/user/settings/interface.json",
  memory: "data/user/settings/main.yaml",
  llm: "data/user/settings/model_catalog.json",
  embedding: "data/user/settings/model_catalog.json",
  search: "data/user/settings/model_catalog.json",
  tts: "data/user/settings/model_catalog.json",
  stt: "data/user/settings/model_catalog.json",
  imagegen: "data/user/settings/model_catalog.json",
  videogen: "data/user/settings/model_catalog.json",
  tools: "data/user/settings/interface.json",
  attachments: "data/user/settings/system.json",
  capabilities: "data/user/settings/main.yaml · agents.yaml",
  "agent-claude-code": "data/user/settings/subagent.json",
  "agent-codex": "data/user/settings/subagent.json",
  "agent-grok": "data/user/settings/subagent.json",
  "agent-antigravity": "data/user/settings/subagent.json",
  "agent-kimi": "data/user/settings/subagent.json",
  "agent-opencode": "data/user/settings/subagent.json",
  "agent-mimo": "data/user/settings/subagent.json",
};

export function storagePathFor(
  pathname: string,
  activeSection?: string | null,
): string | null {
  if (pathname === SETTINGS_HUB_HREF) {
    return activeSection ? (STORAGE_PATHS[activeSection] ?? null) : null;
  }
  const key = resolveSettingsKey(pathname.replace(/^\/settings[\/#]?/, ""));
  if (key === "general") return "data/user/settings/interface.json";
  if (key.startsWith("agent-")) return "data/user/settings/subagent.json";
  return STORAGE_PATHS[key] ?? STORAGE_PATHS[pathname] ?? null;
}
