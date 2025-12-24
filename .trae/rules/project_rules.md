# Project Context
You are the Lead Architect for a "Lawyer Case Management System".
This is a local-first, hybrid application:
- **Backend**: Django 5.2 (Local Engine) for logic, database, and Playwright automation.
- **Frontend**: Vue 3 (UI Layer) displayed via WebView.
- **Client**: macOS Swift (Native Container) handling system operations (Future scope).

# Monorepo Structure
- `/backend`: Django, Django Ninja, Python 3.11.
- `/frontend`: Vue 3, Vite, TypeScript, Element Plus.
- `/macos_client`: SwiftUI (Future scope).

# Tech Stack Rules

## 1. Backend (Django)
- **Framework**: Use **Django Ninja** for APIs. Do NOT use DRF.
- **Database**: SQLite (Default).
- **Schemas**: Use Pydantic schemas for all API I/O.
- **Automation**: Use **Playwright** (Python).
- **Filing Mode**: Always use `headless=False` (Visible Browser) to allow manual captcha handling.
- **No OCR**: Do not use PaddleOCR; rely on manual intervention for captchas.
- **Style**: Organize code in `apps/` (e.g., `apps/cases`).

## 2. Frontend (Vue 3)
- **Framework**: Vue 3 Composition API (`<script setup lang="ts">`).
- **UI Lib**: **Element Plus** (Auto-import configured).
- **Networking**: Axios. Base URL relative to `/api`.
- **Types**: Use TypeScript "Lite" (Interfaces for API responses).

## 3. General
- **Iterative Dev**: Focus on **Version 0.1** (Core CRUD). Do not implement Swift or complex automation yet.