"""Utility sub-package — cross-cutting helpers shared across the app.

Modules
-------
logger          : Logging configuration (setup_logging)
document_loader : PDF / DOCX / PPTX text extraction and chunking
history_store   : Markdown-based conversation history with relevance search
prompts         : LangChain prompt templates for all agents
state           : Shared runtime state (e.g. LLM concurrency semaphore)
"""
