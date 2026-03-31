import { redirect } from 'next/navigation'

export default function RootPage() {
  // Redirect to chat page
  redirect('/chat')
}
