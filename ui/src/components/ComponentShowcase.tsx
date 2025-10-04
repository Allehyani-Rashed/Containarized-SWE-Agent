/**
 * Component Showcase
 *
 * This file demonstrates all reusable components in action.
 * Use this as a reference for component usage patterns.
 */

import Card from './Card';
import Button from './Button';
import { TextInput, TextArea, Select } from './Input';
import StatusBadge from './StatusBadge';
import InfoPanel, { InfoList, InfoItem } from './InfoPanel';
import Icon from './Icon';

function ComponentShowcase() {
  return (
    <div style={{ padding: '2rem', display: 'flex', flexDirection: 'column', gap: '2rem' }}>
      {/* Card Examples */}
      <section>
        <h2>Card Component</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1rem' }}>
          <Card>
            <h3>Default Card</h3>
            <p>This is a standard card with default styling.</p>
          </Card>

          <Card variant="icon" icon={<Icon type="rocket" size={24} />} iconColor="blue">
            <div>
              <h3>Icon Card</h3>
              <p>Card with colored icon on the left.</p>
            </div>
          </Card>

          <Card variant="status" statusIndicator={<StatusBadge status="active" />}>
            <h3>Status Card</h3>
            <p>Card with status indicator.</p>
          </Card>
        </div>
      </section>

      {/* Button Examples */}
      <section>
        <h2>Button Component</h2>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem' }}>
          <Button variant="primary">Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="success">Success</Button>
          <Button variant="danger">Danger</Button>
          <Button variant="ghost">Ghost</Button>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', marginTop: '1rem' }}>
          <Button variant="primary" size="small">Small</Button>
          <Button variant="primary" size="medium">Medium</Button>
          <Button variant="primary" size="large">Large</Button>
        </div>
      </section>

      {/* Input Examples */}
      <section>
        <h2>Input Components</h2>
        <div style={{ display: 'grid', gap: '1rem', maxWidth: '500px' }}>
          <TextInput
            label="Project Name"
            placeholder="Enter project name..."
            required
          />

          <TextInput
            label="Email"
            type="email"
            hint="We'll never share your email"
          />

          <TextArea
            label="Description"
            placeholder="Enter description..."
            rows={4}
            maxLength={240}
            showCharCount
          />

          <Select
            label="Model"
            placeholder="Select a model..."
            options={[
              { value: 'gpt4', label: 'GPT-4 Turbo' },
              { value: 'gpt3', label: 'GPT-3.5' },
            ]}
          />
        </div>
      </section>

      {/* StatusBadge Examples */}
      <section>
        <h2>Status Badge Component</h2>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem' }}>
          <StatusBadge status="pending" />
          <StatusBadge status="running" />
          <StatusBadge status="done" />
          <StatusBadge status="failed" />
          <StatusBadge status="aborted" />
          <StatusBadge status="active" dot />
          <StatusBadge status="online" dot />
          <StatusBadge status="verified" />
          <StatusBadge status="error" />
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', marginTop: '1rem' }}>
          <StatusBadge status="running" size="small" />
          <StatusBadge status="running" size="medium" />
          <StatusBadge status="running" size="large" />
        </div>
      </section>

      {/* InfoPanel Examples */}
      <section>
        <h2>Info Panel Component</h2>
        <div style={{ display: 'grid', gap: '1rem' }}>
          <InfoPanel
            title="Credential Status"
            icon={<Icon type="key" size={20} />}
            iconColor="green"
            variant="success"
            statusIndicator={<StatusBadge status="verified" />}
            actions={
              <>
                <Button variant="primary" size="small">Verify</Button>
                <Button variant="ghost" size="small">Clear</Button>
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

          <InfoPanel
            title="System Status"
            icon={<Icon type="alert" size={20} />}
            iconColor="orange"
            variant="warning"
          >
            <p>Some services may be experiencing issues.</p>
          </InfoPanel>

          <InfoPanel
            title="Project Information"
            icon={<Icon type="folder" size={20} />}
            iconColor="blue"
          >
            <InfoList columns={1}>
              <InfoItem label="Repository" value="company/frontend-dashboard" />
              <InfoItem label="Default Branch" value="main" />
              <InfoItem label="Active Tasks" value="3" />
            </InfoList>
          </InfoPanel>
        </div>
      </section>
    </div>
  );
}

export default ComponentShowcase;
