# Reusable UI Components

This directory contains reusable UI components based on the UX Pilot design system. All components follow the dark theme aesthetic with consistent styling, proper TypeScript typing, and accessibility features.

## Components

### 1. Card

A versatile card component with multiple variants for different use cases.

**Variants:**
- `default` - Standard card with padding
- `icon` - Card with colored icon circle on the left
- `status` - Card with status indicator

**Props:**
- `variant?: 'default' | 'icon' | 'status'`
- `icon?: ReactNode` - Icon to display (for icon variant)
- `iconColor?: 'blue' | 'green' | 'orange' | 'purple' | 'red' | 'cyan'`
- `statusIndicator?: ReactNode` - Status element (for status variant)
- `onClick?: () => void` - Makes card clickable
- `className?: string`

**Example:**
```tsx
import { Card, StatusBadge } from '../components';

// Default card
<Card>
  <h3>Project Summary</h3>
  <p>Content goes here</p>
</Card>

// Icon card
<Card variant="icon" icon="🚀" iconColor="blue">
  <h3>Task Submission</h3>
  <p>Submit new tasks</p>
</Card>

// Status card
<Card variant="status" statusIndicator={<StatusBadge status="active" />}>
  <h3>Frontend Dashboard</h3>
</Card>

// Clickable card
<Card onClick={() => navigate('/project/1')}>
  <h3>Click me</h3>
</Card>
```

---

### 2. Button

Button component with multiple variants and sizes.

**Variants:**
- `primary` - Blue primary button
- `secondary` - Gray secondary button
- `success` - Green success button
- `danger` - Red danger/delete button
- `ghost` - Transparent with border

**Sizes:**
- `small` - Compact button
- `medium` - Default size
- `large` - Large button

**Props:**
- `variant?: 'primary' | 'secondary' | 'success' | 'danger' | 'ghost'`
- `size?: 'small' | 'medium' | 'large'`
- `icon?: ReactNode` - Icon element
- `iconPosition?: 'left' | 'right'`
- `fullWidth?: boolean` - Stretch to full width
- All standard HTML button attributes

**Example:**
```tsx
import { Button } from '../components';

// Primary button
<Button variant="primary" onClick={handleSubmit}>
  Submit Task
</Button>

// Danger button with icon
<Button variant="danger" size="small" icon="🗑️">
  Delete
</Button>

// Ghost button
<Button variant="ghost" onClick={handleCancel}>
  Cancel
</Button>

// Full width success button
<Button variant="success" fullWidth>
  Create Project
</Button>
```

---

### 3. Input Components

Form input components with consistent dark theme styling.

#### TextInput

Single-line text input with optional icon, label, error, and hint.

**Props:**
- `label?: string`
- `error?: string` - Error message to display
- `hint?: string` - Helper text
- `required?: boolean` - Shows asterisk
- `icon?: ReactNode` - Left icon
- All standard HTML input attributes

**Example:**
```tsx
import { TextInput } from '../components';

<TextInput
  label="Project Name"
  placeholder="My Awesome Project"
  required
  value={name}
  onChange={(e) => setName(e.target.value)}
  hint="Enter a descriptive name"
/>

<TextInput
  label="Email"
  type="email"
  error="Invalid email format"
/>
```

#### TextArea

Multi-line textarea with optional character count.

**Props:**
- `label?: string`
- `error?: string`
- `hint?: string`
- `required?: boolean`
- `rows?: number` - Default: 4
- `maxLength?: number`
- `showCharCount?: boolean` - Show character counter
- All standard HTML textarea attributes

**Example:**
```tsx
import { TextArea } from '../components';

<TextArea
  label="Task Instructions"
  placeholder="Describe what you want..."
  rows={6}
  maxLength={240}
  showCharCount
  value={prompt}
  onChange={(e) => setPrompt(e.target.value)}
  required
/>
```

#### Select

Dropdown select with optional predefined options.

**Props:**
- `label?: string`
- `error?: string`
- `hint?: string`
- `required?: boolean`
- `options?: Array<{ value: string; label: string; disabled?: boolean }>`
- `placeholder?: string`
- All standard HTML select attributes

**Example:**
```tsx
import { Select } from '../components';

// With options array
<Select
  label="AI Model"
  options={[
    { value: 'gpt4', label: 'GPT-4 Turbo' },
    { value: 'gpt3', label: 'GPT-3.5' }
  ]}
  value={model}
  onChange={(e) => setModel(e.target.value)}
  required
/>

// With children
<Select label="Project" placeholder="Select a project...">
  <option value="1">Frontend Dashboard</option>
  <option value="2">API Gateway</option>
</Select>
```

---

### 4. StatusBadge

Pill-shaped status indicator with color coding.

**Status Types:**
- `pending` - Yellow
- `running` - Blue
- `done` - Green
- `failed` - Red
- `aborted` - Gray
- `active` - Green
- `error` - Red
- `idle` - Yellow
- `verified` - Green
- `configured` - Green
- `missing` - Red
- `selected` - Blue
- `online` - Green (with pulse animation)
- `offline` - Gray

**Props:**
- `status: StatusType`
- `label?: string` - Override default label
- `icon?: ReactNode` - Optional icon
- `dot?: boolean` - Show pulsing dot
- `size?: 'small' | 'medium' | 'large'`

**Example:**
```tsx
import { StatusBadge } from '../components';

<StatusBadge status="running" />
<StatusBadge status="done" label="Completed" />
<StatusBadge status="online" dot size="small" />
<StatusBadge status="failed" icon="⚠️" />
```

---

### 5. InfoPanel

Information panel component with optional icon, status indicator, and actions.

**Variants:**
- `default` - Standard panel
- `success` - Green border/background
- `warning` - Yellow border/background
- `error` - Red border/background
- `info` - Blue border/background

**Props:**
- `title: string`
- `icon?: ReactNode`
- `iconColor?: 'blue' | 'green' | 'orange' | 'purple' | 'red' | 'cyan'`
- `statusIndicator?: ReactNode`
- `actions?: ReactNode`
- `variant?: 'default' | 'success' | 'warning' | 'error' | 'info'`

**Helper Components:**
- `InfoList` - Container for InfoItems with column layout
- `InfoItem` - Key-value pair display

**Example:**
```tsx
import { InfoPanel, InfoList, InfoItem, StatusBadge, Button } from '../components';

<InfoPanel
  title="Credential Status"
  icon="🔑"
  iconColor="green"
  variant="success"
  statusIndicator={<StatusBadge status="verified" />}
  actions={
    <>
      <Button variant="primary">Verify</Button>
      <Button variant="ghost">Clear</Button>
    </>
  }
>
  <InfoList columns={2}>
    <InfoItem label="GitLab PAT" value="Configured" />
    <InfoItem label="Last Updated" value="2 hours ago" />
    <InfoItem label="Host" value="gitlab.com" />
    <InfoItem label="Verification" value="Verified" />
  </InfoList>
</InfoPanel>
```

---

## Import Patterns

All components can be imported from the components index:

```tsx
import {
  Card,
  Button,
  TextInput,
  TextArea,
  Select,
  StatusBadge,
  InfoPanel,
  InfoList,
  InfoItem
} from '../components';
```

Or import individually:

```tsx
import Card from '../components/Card';
import Button from '../components/Button';
```

---

## Styling

All components use dedicated CSS files that follow the dark theme design system:

- **Background**: `rgba(15, 23, 42, 0.7)`
- **Border**: `rgba(148, 163, 184, 0.25)`
- **Text**: `#e2e8f0`
- **Primary**: Blue (`rgba(59, 130, 246, *)`)
- **Success**: Green (`rgba(34, 197, 94, *)`)
- **Warning**: Yellow (`rgba(251, 191, 36, *)`)
- **Danger**: Red (`rgba(248, 113, 113, *)`)

Components are designed to work seamlessly with the existing App.css styling.

---

## Accessibility

All components include proper accessibility features:

- Semantic HTML elements
- ARIA attributes where appropriate
- Keyboard navigation support
- Focus visible states
- Error announcements for form inputs
- Proper label associations

---

## TypeScript

All components are fully typed with exported interfaces:

```tsx
import type { CardProps, ButtonProps, StatusType } from '../components';
```
