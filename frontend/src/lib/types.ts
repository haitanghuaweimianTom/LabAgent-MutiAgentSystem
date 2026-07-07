export interface Message {
  id: string;
  sender: string;
  sender_label: string;
  content: string;
  type: string;
  timestamp: string;
}

export type TaskStatus =
  | 'idle'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'paused'
  | 'phase1'
  | 'phase2'
  | 'retrying'
  | 'pending'
  | 'preflight_running'
  | 'self_collecting_data'
  | 'iterating_solver'
  | 'cannot_solve';
