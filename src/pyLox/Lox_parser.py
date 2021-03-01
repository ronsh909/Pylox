import sys
from token_type import TokenType
from function_types import FunctionType
from token import Token
from error_handler import ErrorHandler
from stmt import Stmt, Expression, Print, Var, Block, If, While, Fun, Return, Break
from expr import Expr,  Assign, Binary, Conditional, Grouping, Literal, Logical, Unary, Variable, Function, Call
from var_state import VarState

class Parser:

    class ParseError(RuntimeError):
        def __init__(self, message):
            super().__init__(message)

    def __init__(self, tokens: list[Token], error_handler: ErrorHandler):
        self.tokens = tokens
        self.error_handler = error_handler
        self.current = 0    
        self.loop_depth = 0
    
    def parse(self) -> list[Stmt]:
        statements = []
        while not self.is_at_end():
            statements.append(self.declaration())
        return statements

    def declaration(self) -> Stmt:
        try:
            if self.match(TokenType.VAR):
                return self.var_declaration()
            if self.check(TokenType.FUN) and self.check_next(TokenType.IDENTIFIER):
                self.consume(TokenType.FUN, None)
                return self.function("function")
            return self.statement()
        except Parser.ParseError as error:
            self.synchronize()
            return None
    
    def var_declaration(self) -> Stmt:
        name = self.consume(TokenType.IDENTIFIER, "Expect variable name.")
        initializer = None
        if self.match(TokenType.EQUAL):
            initializer = self.expression()
        self.consume(TokenType.SEMICOLON, "Expect semicolon after variable declaration.")
        return Var(name, initializer)

    def function(self, kind: str) -> Stmt:
        name = self.consume(TokenType.IDENTIFIER,f"Expect {kind} name.")
        return Fun(name, self.function_body(kind))

    def function_body(self, kind: str) -> Function:
        self.consume(TokenType.LEFT_PAREN,f"Expect '(' after {kind} name.")
        params = []
        if not self.check(TokenType.RIGHT_PAREN):
            while True:
                if len(params) >= 255:
                    self.error(self.peek(),"Can't have more than 255 parameters.")
                params.append(self.consume(TokenType.IDENTIFIER,"Expect parameter name."))
                if not self.match(TokenType.COMMA):
                    break
        self.consume(TokenType.RIGHT_PAREN,"Expect ')' after parameters.")
        self.consume(TokenType.LEFT_BRACE,"Expect '{ before " + kind + " body.")
        body = self.block_statement()
        return Function(params, body, FunctionType.FUNCTION)
        

    def statement(self) -> Stmt:
        if self.match(TokenType.IF):
            return self.if_statement()
        if self.match(TokenType.WHILE):
            return self.while_statement()
        if self.match(TokenType.FOR):
            return self.for_statement()
        if self.match(TokenType.BREAK):
            return self.break_statement()
        if self.match(TokenType.PRINT):
            return self.print_statement()
        if self.match(TokenType.RETURN):
            return self.return_statement()
        if self.match(TokenType.LEFT_BRACE):
            return Block(self.block_statement())
        return self.expression_statement()

    def print_statement(self) -> Stmt:
        value = self.expression()
        self.consume(TokenType.SEMICOLON, "Expect ';' after value.")
        return Print(value)

    def block_statement(self) -> list[Stmt]:
        statements = []
        while (not self.check(TokenType.RIGHT_BRACE)) and not self.is_at_end():
            statements.append(self.declaration())
        self.consume(TokenType.RIGHT_BRACE,"Expect '}' after block.")
        return statements
        
    def expression_statement(self) -> Expression:
        expr = self.expression()
        self.consume(TokenType.SEMICOLON, "Expect ';' after expression.")
        return Expression(expr)

    def if_statement(self) -> If:
        self.consume(TokenType.LEFT_PAREN,"Expect '(' after 'if'.")
        condition = self.expression()
        self.consume(TokenType.RIGHT_PAREN,"Expect ')' after 'if' condition.")
        then_branch = self.statement()
        else_branch = None
        if self.match(TokenType.ELSE):
            else_branch = self.statement()
        return If(condition, then_branch, else_branch)
    
    def while_statement(self) -> While:
        self.consume(TokenType.LEFT_PAREN,"Expect '(' after 'while'.")
        condition = self.expression()
        self.consume(TokenType.RIGHT_PAREN,"Expect ')' after 'while'")
        try:
            self.loop_depth += 1
            body = self.statement()
            return While(condition, body)
        finally:
            self.loop_depth -= 1

    def for_statement(self) -> Stmt:
        self.consume(TokenType.LEFT_PAREN,"Expect '(' after 'for'.")
        initializer = None
        if self.match(TokenType.VAR):
            initializer = self.var_declaration()
        elif not self.match(TokenType.SEMICOLON):
            initializer = self.expression_statement()
        condition = None
        if not self.check(TokenType.SEMICOLON):
            condition = self.expression()
        self.consume(TokenType.SEMICOLON,"Expect ';' after 'for' condition.")
        increment = None
        if not self.check(TokenType.RIGHT_PAREN):
            increment = self.expression()
        self.consume(TokenType.RIGHT_PAREN,"Expect ')' after 'for' clauses.")
        try:
            self.loop_depth += 1
            body = self.statement()
            if increment is not None:
                body = Block([body, Expression(increment)])
            if condition is None:
                condition = Literal(True)
            body = While(condition, body)
            if initializer is not None:
                body = Block([initializer, body])
                return body 
        finally:
            self.loop_depth -= 1
        
    def break_statement(self) -> Break:
        if self.loop_depth == 0:
            self.error(self.previous(), "Must be inside loop to use 'break'.")
        self.consume(TokenType.SEMICOLON,"Expect ';' after break.")
        return Break()

    def return_statement(self) -> Return:
        keyword = self.previous()
        value = None
        if not self.check(TokenType.SEMICOLON):
            value = self.expression()
        self.consume(TokenType.SEMICOLON,"Expect ';' after return value.")
        return Return(keyword,value)

    def expression(self) -> Expr:
        return self.comma_op()

    ''' In C, the comma operator has the lowest precedence,
     and therefore it will be the first "level" in the descent
     '''
    def comma_op(self) -> Expr:
        expr = self.assignment()
        while self.match(TokenType.COMMA):
            operator = self.previous()
            right = self.assignment()
            expr = Binary(expr, operator, right)
        return expr

    def assignment(self) -> Expr:
        expr = self.conditional()
        if self.match(TokenType.EQUAL):
            equals = self.previous()
            value = self.assignment()
            if type(expr) is Variable:
                name = expr.name
                return Assign(name, value)
            self.error(equals, "Invalid assignment target.")
        return expr


    def conditional(self) -> Expr:
        expr = self.or_expr()
        if self.match(TokenType.QUESTION):
            then_branch = self.or_expr()
            self.consume(TokenType.COLON, " Expect ':' seperator after then branch in ternary conditional.")
            else_branch = self.or_expr()
            expr = Conditional(expr, then_branch, else_branch)
        return expr

    def or_expr(self) -> Expr:
        expr = self.and_expr()
        while self.match(TokenType.OR):
            operator = self.previous()
            right = self.and_expr()
            expr = Logical(expr, operator, right)
        return expr

    def and_expr(self) -> Expr:
        expr = self.equality()
        while self.match(TokenType.AND):
            operator = self.previous()
            right = self.equality()
            expr = Logical(expr, operator, right)
        return expr

    def equality(self) -> Expr:
        expr = self.comparison()
        while self.match(TokenType.BANG_EQUAL, TokenType.EQUAL_EQUAL):
            operator = self.previous()
            right = self.comparison()
            expr = Binary(expr, operator, right)
        return expr

    def comparison(self) -> Expr:
        expr = self.term()
        while self.match(TokenType.GREATER, TokenType.GREATER_EQUAL, TokenType.LESS, TokenType.LESS_EQUAL):
            operator = self.previous()
            right = self.term()
            expr = Binary(expr, operator, right)
        return expr

    def term(self) -> Expr:
        expr = self.factor()
        while self.match(TokenType.PLUS, TokenType.MINUS):
            operator = self.previous()
            right = self.factor()
            expr = Binary(expr, operator, right)
        return expr
    
    def factor(self) -> Expr:
        expr = self.unary()
        while self.match(TokenType.SLASH, TokenType.STAR):
            operator = self.previous()
            right = self.unary()
            expr = Binary(expr, operator, right)
        return expr

    def unary(self) -> Expr:
        if self.match(TokenType.BANG, TokenType.MINUS):
            operator = self.previous()
            right = self.unary()
            return Unary(operator, right)
        return self.call()

    def call(self) -> Expr:
        expr = self.primary()
        while True:
            if self.match(TokenType.LEFT_PAREN):
                expr = self.finish_call(expr)
            else:
                break   
        return expr

    def primary(self) -> Expr:
        if self.match(TokenType.TRUE):
            return Literal(True)
        if self.match(TokenType.FALSE):
            return Literal(False)
        if self.match(TokenType.NIL):
            return Literal(None)
        if self.match(TokenType.NUMBER, TokenType.STRING):
            return Literal(self.previous().literal)
        if self.match(TokenType.FUN):
            return self.function_body("function")
        if self.match(TokenType.LEFT_PAREN):
            expr = self.expression()
            self.consume(TokenType.RIGHT_PAREN, "Expect ')' after expression.")
            return Grouping(expr)
        if self.match(TokenType.IDENTIFIER):
            return Variable(self.previous())
        # The following if clauses are productions for missing left operands - "error productions"
        if self.match(TokenType.COMMA):
            self.error(self.previous(), "Missing left-hand operand.")
            self.comma_op()
            return None
        if self.match(TokenType.BANG_EQUAL, TokenType.EQUAL_EQUAL):
            self.error(self.previous(), "Missing left-hand operand.")
            self.equality()
            return None
        if self.match(TokenType.QUESTION):
            self.error(self.previous(), "Missing condition expression for ternary conditional.")
            self.conditional()
            return None
        if self.match(TokenType.GREATER, TokenType.GREATER_EQUAL, TokenType.LESS, TokenType.LESS_EQUAL):
            self.error(self.previous(), "Missing left-hand operand.")
            self.comparison()
            return None
        if self.match(TokenType.PLUS):
            self.error(self.previous(), "Missing left-hand operand.")
            self.term()
            return None
        if self.match(TokenType.SLASH, TokenType.STAR):
            self.error(self.previous(), "Missing left-hand operand.")
            self.factor()
            return None
        self.error_handler.error_on_token(self.peek(), "Expect expression.")

    def finish_call(self, callee: Call) -> Expr:
        arguments = []
        if not self.check(TokenType.RIGHT_PAREN):
            while True:
                if len(arguments) >= 255:
                    self.error(self.peek(), "Cant have more than 255 arguments. ")
                arguments.append(self.conditional())
                if not self.match(TokenType.COMMA):
                    break
        paren = self.consume(TokenType.RIGHT_PAREN,"Expect ')' after arguments.")
        return Call(callee, paren, arguments)
        


    def match(self, *types) -> bool:
        for type_ in types:
            if self.check(type_):
                self.advance()
                return True
        return False
    
    def check(self, type_: TokenType) -> bool:
        if self.is_at_end():
            return False
        return self.peek().type_ == type_
    
    def check_next(self, type_: TokenType) -> bool:
        if self.is_at_end():
            return False
        if self.tokens[self.current+1].type_ == TokenType.EOF:
            return False
        return self.tokens[self.current+1].type_ == type_
    
    def is_at_end(self) -> bool:
        return self.peek().type_ == TokenType.EOF
    
    def peek(self) -> Token:
        return self.tokens[self.current]

    def advance(self) -> Token:
        if not self.is_at_end():
            self.current += 1
        return self.previous()

    def previous(self) -> Token:
        return self.tokens[self.current-1]
    
    def consume(self, type_: TokenType, message: str) -> Token:
        if self.check(type_):
            return self.advance()
        self.error(self.peek(), message)

    def error(self, token: Token, message: str) -> ParseError:
        self.error_handler.error_on_token(token, message)
        return Parser.ParseError("")

    def synchronize(self):
        self.advance()
        keywords = {TokenType.CLASS, TokenType.FUN, TokenType.VAR, TokenType.FOR, TokenType.IF, TokenType.WHILE,  TokenType.PRINT, TokenType.RETURN}
        while not self.is_at_end():
            if self.previous().type_ == TokenType.SEMICOLON:
                return
            if self.peek().type_ in keywords:
                return
            self.advance()
