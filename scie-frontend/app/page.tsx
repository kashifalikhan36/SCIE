import { GlowyWavesHero } from "@/components/ui/glowy-waves-hero-shadcnui"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Activity, Server, Radio, Users } from "lucide-react"

export default function Home() {
  return (
    <div className="flex flex-col gap-6">
      <div className="relative h-[400px] w-full overflow-hidden rounded-xl border border-border/40">
        {/* We reuse the GlowyWavesHero but restrict its height so it doesn't take over the entire dashboard */}
        <div className="absolute inset-0 scale-[0.6] origin-top">
           <GlowyWavesHero />
        </div>
        <div className="absolute inset-0 bg-gradient-to-t from-background via-background/20 to-transparent pointer-events-none" />
        <div className="absolute bottom-6 left-6 z-20">
          <h1 className="text-4xl font-bold tracking-tight text-foreground">Welcome to Sherlock AI</h1>
          <p className="text-muted-foreground mt-2 max-w-lg">
            The intelligent candidate identification platform. Monitor live interviews, review past evidence, and analyze engine confidence in real-time.
          </p>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card className="bg-background/60 backdrop-blur border-border/40">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">System Status</CardTitle>
            <Server className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-500">Operational</div>
            <p className="text-xs text-muted-foreground">All 10 intelligence engines online</p>
          </CardContent>
        </Card>

        <Card className="bg-background/60 backdrop-blur border-border/40">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Active Interviews</CardTitle>
            <Radio className="h-4 w-4 text-blue-500 animate-pulse" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">3</div>
            <p className="text-xs text-muted-foreground">Currently streaming ingestion</p>
          </CardContent>
        </Card>

        <Card className="bg-background/60 backdrop-blur border-border/40">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Historical Candidates</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">12,401</div>
            <p className="text-xs text-muted-foreground">+241 this week</p>
          </CardContent>
        </Card>

        <Card className="bg-background/60 backdrop-blur border-border/40">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Avg Fusion Latency</CardTitle>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">8.4ms</div>
            <p className="text-xs text-muted-foreground">P99 across all nodes</p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
