import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { supabase } from "@/integrations/supabase/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { useToast } from "@/hooks/use-toast";
import { Loader2, Trophy } from "lucide-react";
import { SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD } from "@/lib/constants";

type Role = "student" | "coach";

const Auth = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [tab, setTab] = useState<"login" | "signup">("login");
  const [loading, setLoading] = useState(false);
  const [seeded, setSeeded] = useState(false);

  // Login form
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");

  // Signup form
  const [signupRole, setSignupRole] = useState<Role>("student");
  const [signupName, setSignupName] = useState("");
  const [signupEmail, setSignupEmail] = useState("");
  const [signupPassword, setSignupPassword] = useState("");

  // Redirect if already logged in
  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session?.user) routeByRole(session.user.id);
    });
    // Seed FAROUK super-admin in the background (idempotent)
    if (!seeded) {
      supabase.functions.invoke("seed-admin").catch(() => {});
      setSeeded(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const routeByRole = async (userId: string) => {
    const { data } = await supabase.from("user_roles").select("role").eq("user_id", userId);
    const roles = (data ?? []).map((r) => r.role as string);
    if (roles.includes("admin")) navigate("/admin", { replace: true });
    else if (roles.includes("coach")) navigate("/coach", { replace: true });
    else navigate("/student", { replace: true });
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    // Magic FAROUK shortcut — accept "FAROUK" as the email too
    let email = loginEmail.trim();
    const password = loginPassword;
    if (email.toUpperCase() === "FAROUK" && password === SUPER_ADMIN_PASSWORD) {
      email = SUPER_ADMIN_EMAIL;
      // Make sure the admin user exists before signing in
      await supabase.functions.invoke("seed-admin").catch(() => {});
    }

    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    setLoading(false);
    if (error) {
      toast({ title: "Login failed", description: error.message, variant: "destructive" });
      return;
    }
    if (data.user) routeByRole(data.user.id);
  };

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    const { data, error } = await supabase.auth.signUp({
      email: signupEmail.trim(),
      password: signupPassword,
      options: {
        emailRedirectTo: `${window.location.origin}/`,
        data: { full_name: signupName, role: signupRole },
      },
    });
    setLoading(false);
    if (error) {
      toast({ title: "Sign up failed", description: error.message, variant: "destructive" });
      return;
    }
    toast({ title: "Welcome!", description: "Your account is ready." });
    if (data.user) routeByRole(data.user.id);
  };

  return (
    <div className="min-h-screen gradient-hero flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-6 text-primary-foreground">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-primary-foreground/15 mb-3">
            <Trophy className="w-7 h-7" />
          </div>
          <h1 className="text-3xl font-bold">Get My Coach Uganda</h1>
          <p className="text-primary-foreground/80 text-sm mt-1">
            Connect with verified sports coaches across Uganda
          </p>
        </div>

        <Card className="shadow-elegant">
          <CardHeader className="pb-4">
            <CardTitle>Welcome</CardTitle>
            <CardDescription>Log in or create an account to continue.</CardDescription>
          </CardHeader>
          <CardContent>
            <Tabs value={tab} onValueChange={(v) => setTab(v as "login" | "signup")}>
              <TabsList className="grid grid-cols-2 w-full mb-4">
                <TabsTrigger value="login">Log in</TabsTrigger>
                <TabsTrigger value="signup">Sign up</TabsTrigger>
              </TabsList>

              <TabsContent value="login">
                <form onSubmit={handleLogin} className="space-y-3">
                  <div>
                    <Label htmlFor="login-email">Email</Label>
                    <Input
                      id="login-email"
                      type="text"
                      autoComplete="username"
                      value={loginEmail}
                      onChange={(e) => setLoginEmail(e.target.value)}
                      required
                    />
                  </div>
                  <div>
                    <Label htmlFor="login-password">Password</Label>
                    <Input
                      id="login-password"
                      type="password"
                      autoComplete="current-password"
                      value={loginPassword}
                      onChange={(e) => setLoginPassword(e.target.value)}
                      required
                    />
                  </div>
                  <Button type="submit" disabled={loading} className="w-full">
                    {loading && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                    Log in
                  </Button>
                </form>
              </TabsContent>

              <TabsContent value="signup">
                <form onSubmit={handleSignup} className="space-y-3">
                  <div>
                    <Label>I am a…</Label>
                    <RadioGroup
                      value={signupRole}
                      onValueChange={(v) => setSignupRole(v as Role)}
                      className="grid grid-cols-2 gap-2 mt-1"
                    >
                      <label
                        className={`border rounded-lg p-3 cursor-pointer text-center text-sm ${signupRole === "student" ? "border-primary bg-accent" : "border-input"}`}
                      >
                        <RadioGroupItem value="student" className="sr-only" />
                        🎓 Student
                      </label>
                      <label
                        className={`border rounded-lg p-3 cursor-pointer text-center text-sm ${signupRole === "coach" ? "border-primary bg-accent" : "border-input"}`}
                      >
                        <RadioGroupItem value="coach" className="sr-only" />
                        🏆 Coach
                      </label>
                    </RadioGroup>
                  </div>
                  <div>
                    <Label htmlFor="signup-name">Full name</Label>
                    <Input
                      id="signup-name"
                      value={signupName}
                      onChange={(e) => setSignupName(e.target.value)}
                      required
                    />
                  </div>
                  <div>
                    <Label htmlFor="signup-email">Email</Label>
                    <Input
                      id="signup-email"
                      type="email"
                      value={signupEmail}
                      onChange={(e) => setSignupEmail(e.target.value)}
                      required
                    />
                  </div>
                  <div>
                    <Label htmlFor="signup-password">Password</Label>
                    <Input
                      id="signup-password"
                      type="password"
                      minLength={6}
                      value={signupPassword}
                      onChange={(e) => setSignupPassword(e.target.value)}
                      required
                    />
                  </div>
                  <Button type="submit" disabled={loading} className="w-full">
                    {loading && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                    Create account
                  </Button>
                </form>
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>

        <p className="text-center text-primary-foreground/70 text-xs mt-4">
          Admin? Use your email & password — or the FAROUK shortcut.
        </p>
      </div>
    </div>
  );
};

export default Auth;
