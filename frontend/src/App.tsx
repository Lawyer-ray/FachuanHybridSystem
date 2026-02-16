import { Button } from "@/components/ui/button"

function App() {
  return (
    <div className="min-h-screen bg-background flex items-center justify-center">
      <div className="text-center space-y-4">
        <h1 className="text-4xl font-bold text-foreground">Tailwind + shadcn/ui</h1>
        <p className="text-muted-foreground">配置成功！</p>
        <Button>测试按钮</Button>
      </div>
    </div>
  )
}

export default App
