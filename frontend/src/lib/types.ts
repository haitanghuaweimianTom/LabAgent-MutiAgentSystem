export interface Message {
  id: string;
  sender: string;
  sender_label: string;
  content: string;
  type: string;
  timestamp: string;
}

export type TabType =
  | 'dashboard'
  | 'generate'
  | 'files'
  | 'pdf'
  | 'history'
  | 'agents'
  | 'workflows'
  | 'memory'
  | 'environment'
  | 'settings';

export type TaskStatus =
  | 'idle'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'paused'
  | 'phase1'
  | 'phase2'
  | 'retrying';